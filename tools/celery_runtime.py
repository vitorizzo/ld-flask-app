"""Atomic admission, renewable leases and observable task statistics in Redis."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import threading
import time
from uuid import uuid4

from celery.utils.time import maybe_iso8601

from tools.celery_contexts import canonical_task, job_key, task_context
from tools.redis_utils import get_redis

logger = logging.getLogger(__name__)
LEASE_SECONDS = 180
DEFAULT_QUEUE_SECONDS = 1800
DUE_KEY = "celery:runtime:due"
CONTEXT_KEY = "celery:runtime:context:gestionale"
COMMON = r'''
local now=tonumber(ARGV[1])
local metric=ARGV[3]
local base='celery:runtime:stats:'..metric
local function event(kind,duration)
  redis.call('HINCRBY',base..':total',kind,1)
  local data={kind=kind,time=now,id=ARGV[2]}
  if duration then
    data.duration=duration
    redis.call('HSET',base..':last','duration',duration,'finished_at',now)
    redis.call('HINCRBYFLOAT',base..':total','duration_sum',duration)
    redis.call('HINCRBY',base..':total','duration_count',1)
  end
  redis.call('ZADD',base..':window',now,cjson.encode(data))
  redis.call('ZREMRANGEBYSCORE',base..':window','-inf',now-86400)
  redis.call('EXPIRE',base..':window',172800)
end
'''
RESERVE = COMMON + r'''
local expired_id=''
local old=redis.call('HGET',KEYS[1],'token')
if old and tonumber(redis.call('HGET',KEYS[1],'deadline'))<=now then
  local state=redis.call('HGET',KEYS[1],'state')
  event(state=='queued' and 'expired' or 'lost_worker',nil)
  expired_id=redis.call('HGET',KEYS[1],'task_id')
  redis.call('ZREM','celery:runtime:due',redis.call('HGET',KEYS[1],'member'))
  redis.call('DEL',KEYS[1]); old=nil
end
if old and ARGV[8]~=old then
  event('attempted',nil)
  local state=redis.call('HGET',KEYS[1],'state')
  event(state=='running' and 'skip_running' or 'skip_queued',nil)
  return {0,state,redis.call('HGET',KEYS[1],'task_id')}
end
if not old then event('attempted',nil) end
if old then redis.call('ZREM','celery:runtime:due',redis.call('HGET',KEYS[1],'member')) end
redis.call('HSET',KEYS[1],'token',ARGV[5],'task_id',ARGV[4],'state','queued',
 'deadline',ARGV[6],'member',ARGV[7],'metric',metric)
redis.call('PEXPIRE',KEYS[1],math.max(1000,math.ceil((tonumber(ARGV[6])-now+60)*1000)))
redis.call('ZADD','celery:runtime:due',ARGV[6],ARGV[7])
return {1,'queued',ARGV[4],expired_id}
'''
START = COMMON + r'''
if redis.call('HGET',KEYS[1],'token')~=ARGV[4] then return 0 end
if tonumber(redis.call('HGET',KEYS[1],'deadline'))<=now then return -1 end
redis.call('HSET',KEYS[1],'state','running','deadline',now+tonumber(ARGV[5]))
redis.call('EXPIRE',KEYS[1],tonumber(ARGV[5])+60)
local old_member=redis.call('HGET',KEYS[1],'member')
local member=cjson.decode(old_member); member.state='running'
local new_member=cjson.encode(member)
redis.call('ZREM','celery:runtime:due',old_member)
redis.call('HSET',KEYS[1],'member',new_member)
redis.call('ZADD','celery:runtime:due',now+tonumber(ARGV[5]),new_member)
event('started',nil)
return 1
'''
RENEW = r'''
if redis.call('HGET',KEYS[1],'token')~=ARGV[1] then return 0 end
redis.call('HSET',KEYS[1],'deadline',tonumber(ARGV[2])+tonumber(ARGV[3]))
redis.call('EXPIRE',KEYS[1],tonumber(ARGV[3])+60)
redis.call('ZADD','celery:runtime:due',tonumber(ARGV[2])+tonumber(ARGV[3]),redis.call('HGET',KEYS[1],'member'))
if ARGV[4]=='1' and redis.call('GET',KEYS[2])==ARGV[1] then redis.call('EXPIRE',KEYS[2],tonumber(ARGV[3])) end
return 1
'''
FINISH = COMMON + r'''
if redis.call('HGET',KEYS[1],'token')~=ARGV[4] then return 0 end
if ARGV[5]=='reap' and tonumber(redis.call('HGET',KEYS[1],'deadline'))>now then return 0 end
local kind=ARGV[5]
if kind=='reap' then
  kind=redis.call('HGET',KEYS[1],'state')=='queued' and 'expired' or 'lost_worker'
end
if redis.call('HGET',KEYS[1],'state')=='running' and (kind=='skip_running' or kind=='skipped_other' or kind=='paused') then
  event('skipped_after_start',nil)
end
redis.call('ZREM','celery:runtime:due',redis.call('HGET',KEYS[1],'member'))
redis.call('DEL',KEYS[1])
if kind~='release' then event(kind,ARGV[6]~='' and tonumber(ARGV[6]) or nil) end
return 1
'''
RELEASE_CONTEXT = "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0"


def record(name, kind):
    get_redis().eval(COMMON + "event(ARGV[4],nil); return 1", 0,
                     time.time(), uuid4().hex, canonical_task(name), kind)


def queue_deadline(expires=None, countdown=None, eta=None):
    now = time.time()
    if isinstance(expires, str):
        expires = maybe_iso8601(expires)
    if isinstance(expires, datetime):
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        deadline = expires.timestamp()
    elif expires is not None:
        deadline = now + max(0, float(expires))
    else:
        deadline = now + DEFAULT_QUEUE_SECONDS
    if expires is None and (eta or countdown):
        due = maybe_iso8601(eta) if isinstance(eta, str) else eta
        if due:
            if due.tzinfo is None: due = due.replace(tzinfo=timezone.utc)
            deadline = max(deadline, due.timestamp() + DEFAULT_QUEUE_SECONDS)
        else:
            deadline += max(0, float(countdown or 0))
    return deadline


def reserve(name, task_id, args=None, kwargs=None, expires=None, countdown=None, eta=None, previous=None):
    metric = canonical_task(name)
    token = uuid4().hex
    key = job_key(name, args, kwargs, task_id)
    deadline = queue_deadline(expires, countdown, eta)
    member = json.dumps(dict(key=key, token=token, metric=metric, task_id=task_id, state='queued'), sort_keys=True)
    result = get_redis().eval(RESERVE, 1, key, time.time(), uuid4().hex, metric,
                              task_id, token, deadline, member, previous or '')
    if not result[0]:
        return None, 'skip_' + result[1]
    if len(result) > 3 and result[3]:
        from tools.redis_utils import clear_task_status
        clear_task_status(result[3])
    return dict(key=key, token=token, metric=metric, deadline=deadline, member=member), None


def finish(job, kind='release', duration=None):
    if not job: return False
    return bool(get_redis().eval(FINISH, 1, job['key'], time.time(), uuid4().hex,
                               job['metric'], job['token'], kind, '' if duration is None else duration))


def mark_skipped(task, task_id, reason):
    from celery.result import EagerResult
    result = dict(success=True, skipped=True, reason=reason,
                  message='Occorrenza non accodata: ' + reason)
    task.backend.store_result(task_id, result, 'SUCCESS')
    get_redis().setex('celery:runtime:skipped:' + task_id, 600, reason)
    return EagerResult(task_id, result, 'SUCCESS')


def reap_expired(limit=200):
    r = get_redis()
    for member in r.zrangebyscore(DUE_KEY, '-inf', time.time(), start=0, num=limit):
        job = json.loads(member)
        # A missing key means a lease outlived its cleanup grace period.
        # Remove the orphan index; never remove a newer reservation.
        if not r.exists(job['key']):
            r.eval(COMMON + "if redis.call('ZREM',KEYS[1],ARGV[4])==1 then event(ARGV[5],nil) end return 1",
                   1, DUE_KEY, time.time(), uuid4().hex, job['metric'], member,
                   'expired' if job.get('state') == 'queued' else 'lost_worker')
            from tools.redis_utils import clear_task_status
            clear_task_status(job['task_id'])
            continue
        if finish(job, 'reap'):
            from tools.redis_utils import clear_task_status
            clear_task_status(job['task_id'])
        elif r.hget(job['key'], 'token') != job['token']:
            r.zrem(DUE_KEY, member)


class LeaseLost(RuntimeError):
    pass


@contextmanager
def execution(job, context):
    """One renewable task lease; a shared lock additionally serializes the ERP."""
    r = get_redis()
    has_context = context == 'gestionale'
    if has_context:
        while not r.set(CONTEXT_KEY, job['token'], nx=True, ex=LEASE_SECONDS):
            if time.time() >= job['deadline']:
                finish(job, 'expired')
                raise LeaseLost('Occorrenza scaduta in attesa del gestionale')
            time.sleep(.25)
    stop = threading.Event()
    try:
        started = r.eval(START, 1, job['key'], time.time(), uuid4().hex, job['metric'], job['token'], LEASE_SECONDS)
        if started != 1:
            if started == -1: finish(job, 'expired')
            raise LeaseLost('Prenotazione scaduta o sostituita')
        def renew():
            while not stop.wait(15):
                try:
                    r.eval(RENEW, 2, job['key'], CONTEXT_KEY, job['token'], time.time(), LEASE_SECONDS, int(has_context))
                except Exception:
                    logger.exception('Rinnovo lease Celery non riuscito')
        thread = threading.Thread(target=renew, name='celery-lease', daemon=True)
        thread.start()
        yield
    finally:
        stop.set()
        if has_context: r.eval(RELEASE_CONTEXT, 1, CONTEXT_KEY, job['token'])


def runtime_snapshot(task_names):
    r = get_redis()
    metrics = {canonical_task(name) for name in task_names}
    pipe = r.pipeline()
    names = sorted(metrics)
    for name in names:
        base = 'celery:runtime:stats:' + name
        pipe.hgetall(base + ':total').hgetall(base + ':last').zrangebyscore(base + ':window', time.time()-86400, '+inf')
    values = pipe.execute()
    result = {}
    for index, name in enumerate(names):
        totals, last, events = values[index*3:index*3+3]
        recent = {}; durations = []
        for raw in events:
            event = json.loads(raw); kind = event['kind']
            recent[kind] = recent.get(kind, 0) + 1
            if 'duration' in event: durations.append(event['duration'])
        skipped = sum(recent.get(kind, 0) for kind in ('skip_queued', 'skip_running', 'expired'))
        evaluated = skipped + max(0, recent.get('started', 0) - recent.get('skipped_after_start', 0))
        result[name] = dict(available=True, total={key: float(value) for key, value in totals.items()},
                            recent=recent, skip_percent=round(100*skipped/evaluated,1) if evaluated else 0,
                            last_duration=float(last['duration']) if last.get('duration') else None,
                            average_duration=sum(durations)/len(durations) if durations else None,
                            states=[])
    for key in r.scan_iter('celery:runtime:job:*', count=100):
        job = r.hgetall(key)
        if job.get('metric') in result and float(job.get('deadline', 0)) > time.time():
            result[job['metric']]['states'].append(job.get('state'))
    return result


def reset_totals(task_name):
    r = get_redis()
    # Atomic DEL races safely with Lua increments; rolling 24h history remains.
    r.delete('celery:runtime:stats:' + canonical_task(task_name) + ':total')


def revoked_task(sender=None, request=None, expired=False, **kwargs):
    """Consumer-side cleanup; the Beat reaper is its independent fallback."""
    if request is None: return
    job = (getattr(request, '_request_dict', None) or {}).get('ld_runtime')
    if job:
        try:
            finish(job, 'expired' if expired else 'cancelled')
            from tools.redis_utils import clear_task_status
            clear_task_status(request.id)
        except Exception:
            logger.exception('Cleanup task revocata fallito')


def worker_started(sender=None, **kwargs):
    if sender is None: return
    import os
    try:
        get_redis().setex('celery:runtime:worker_ready:' + sender.hostname, 600, json.dumps({
            'pid': os.getpid(), 'started_at': time.time(),
            'queues': [queue.name for queue in sender.task_consumer.queues],
        }))
    except Exception:
        logger.exception('Registrazione avvio worker Celery fallita')


from celery.signals import task_revoked, worker_ready
task_revoked.connect(revoked_task, weak=False)
worker_ready.connect(worker_started, weak=False)

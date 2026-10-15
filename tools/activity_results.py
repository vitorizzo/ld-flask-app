"""Dispatch durable activity event notifications through the existing Web Push service."""
from datetime import datetime
from extensions import db
from models import ActivityResultNotice, PushSubscription, OperationalActivity, User
from tools.activities import EVENT_LABELS, event_message, visible_query, logger


def dispatch_results():
    from tools.push_notifications import is_push_configured, send_push_to_subscriptions
    if not is_push_configured():
        logger.info('Activity results push deferred: VAPID unavailable')
        return dict(success=True,skipped=True,reason='push_not_configured')
    sent=failed=0
    ids=[n.id for n in ActivityResultNotice.query.filter_by(push_sent_at=None).order_by(ActivityResultNotice.id).limit(100).all()]
    for notice_id in ids:
        notice=ActivityResultNotice.query.filter_by(id=notice_id,push_sent_at=None).with_for_update(skip_locked=True).first()
        if not notice: continue
        row=notice.activity
        try:
            subscriptions=PushSubscription.query.filter_by(user_id=notice.user_id,is_active=True).all()
            user=db.session.get(User,notice.user_id)
            can_open=user is not None and visible_query(user,include_results=True).filter_by(id=row.id).first() is not None
            result=send_push_to_subscriptions(subscriptions,dict(title=EVENT_LABELS.get(notice.event.action,'Aggiornamento attività'),body=row.title+' · '+event_message(notice.event)[:500],
                url=f'/activities?activity={row.id}' if can_open else '/activities',category='activity',tag=f'activity-result-{notice.id}',
                notification_id=f'activity-result-{notice.id}',icon='/static/icons/icon-192.png'),commit=False)
            if not result['failed']:
                notice.push_sent_at=datetime.utcnow();sent+=1
            else:
                failed+=1
                logger.warning('Activity result push failed notice=%s failures=%s',notice.id,result['failed'])
            db.session.commit()
        except Exception:
            db.session.rollback();failed+=1;logger.exception('Activity result dispatch failed notice=%s',notice_id)
    logger.info('Activity results dispatch sent=%s failed=%s',sent,failed)
    return dict(success=not failed,sent=sent,failed=failed)


def enqueue_results():
    from config.tasks import dispatch_activity_results_task
    return dispatch_activity_results_task.delay()

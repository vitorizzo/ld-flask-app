"""Shared operational work, role visibility and supplier-arrival workflows."""
from datetime import datetime
from flask import current_app, g, has_request_context
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from extensions import db
from tools.role_required import meets_minimum_role, resolve_minimum_weight
from models import (AppPreference, Role, User, UserRole, OperationalActivity, ActivityTargetRole, ActivityTargetUser,
                    ActivityEvent, ActivityPhoto, SupplierArrival, ActivityResultRole, ActivityResultUser, ActivityAttachment, ActivityResultNotice)

KINDS = {'check_goods':'Controllare la merce', 'lots':'Inviare i lotti', 'store_goods':'Sistemare i prodotti in magazzino'}
ACTIVE = ('pending','in_progress')
CLOSED = ('completed','not_required','cancelled')
from tools.log_utils import get_logger
logger = get_logger('activities')

CONFIG_KEY = 'activities.supplier_arrival.routing'


def manager(user): return meets_minimum_role(user, "office")


def sees_all(user):
    """Only the named Admin and Dev roles can see every activity."""
    return any(str(role.name or '').strip().casefold() in {'admin', 'dev', 'developer'}
               for role in (user.active_roles or []))


def assigned_query(user):
    query = OperationalActivity.query
    target_minimum = func.coalesce(
        select(Role.weight).where(Role.id == OperationalActivity.target_min_role_id).scalar_subquery(),
        OperationalActivity.target_min_weight,
    )
    if not sees_all(user):
        ids = [role.id for role in user.active_roles]
        assigned_role = db.session.query(ActivityTargetRole.activity_id).filter(
            ActivityTargetRole.activity_id == OperationalActivity.id, ActivityTargetRole.role_id.in_(ids)).exists()
        assigned_user = db.session.query(ActivityTargetUser.activity_id).filter(
            ActivityTargetUser.activity_id == OperationalActivity.id, ActivityTargetUser.user_id == user.id).exists()
        result_role = db.session.query(ActivityResultRole.activity_id).filter(
            ActivityResultRole.activity_id == OperationalActivity.id, ActivityResultRole.role_id.in_(ids)).exists()
        result_user = db.session.query(ActivityResultUser.activity_id).filter(
            ActivityResultUser.activity_id == OperationalActivity.id, ActivityResultUser.user_id == user.id).exists()
        query = query.filter(
            assigned_role | assigned_user | (OperationalActivity.owner_id == user.id)
            | (OperationalActivity.status.in_(CLOSED) & (result_role | result_user))
            | (OperationalActivity.target_min_weight.isnot(None) & (target_minimum <= (user.max_role_weight or 0)))
            | (OperationalActivity.status.in_(CLOSED) & OperationalActivity.result_min_weight.isnot(None) &
               (func.coalesce(select(Role.weight).where(Role.id == OperationalActivity.result_min_role_id).scalar_subquery(), OperationalActivity.result_min_weight) <= (user.max_role_weight or 0)) )
        )
    return query

def family_ids(user):
    tree=assigned_query(user).with_entities(OperationalActivity.id).cte(name='readable_family',recursive=True)
    tree=tree.union_all(select(OperationalActivity.id).where(OperationalActivity.parent_id==tree.c.id))
    return select(tree.c.id)


def visible_query(user, include_results=False):
    if not include_results: return assigned_query(user)
    if sees_all(user): return OperationalActivity.query
    return OperationalActivity.query.filter(OperationalActivity.id.in_(family_ids(user)) | result_access(user))


def can_edit(row,user):
    return manager(user) and (sees_all(user) or OperationalActivity.query.filter(OperationalActivity.id==row.id,OperationalActivity.id.in_(family_ids(user))).first() is not None)


def lock_family(activity_id):
    row=db.session.get(OperationalActivity,activity_id)
    if row is None: return
    chain=[]
    while row is not None:
        if row.id in chain: raise ValueError('Gerarchia attività non valida.')
        chain.append(row.id)
        row=db.session.get(OperationalActivity,row.parent_id) if row.parent_id else None
    # One root lock serializes creation, completion and reopening throughout a tree.
    OperationalActivity.query.filter_by(id=chain[-1]).populate_existing().with_for_update().first()



def result_access(user):
    return db.session.query(ActivityResultNotice.id).filter(
        ActivityResultNotice.activity_id == OperationalActivity.id,
        ActivityResultNotice.user_id == user.id, ActivityResultNotice.cycle == OperationalActivity.cycle).exists() & \
        OperationalActivity.status.in_(('completed', 'not_required', 'cancelled'))


def activity_query(user, detail=False):
    query = visible_query(user, include_results=True).options(selectinload(OperationalActivity.arrival), selectinload(OperationalActivity.owner),
        selectinload(OperationalActivity.targets).selectinload(ActivityTargetRole.role),
        selectinload(OperationalActivity.user_targets).selectinload(ActivityTargetUser.user),
        selectinload(OperationalActivity.result_roles).selectinload(ActivityResultRole.role),
        selectinload(OperationalActivity.result_users).selectinload(ActivityResultUser.user))
    if detail:
        query = query.options(selectinload(OperationalActivity.events).selectinload(ActivityEvent.actor), selectinload(OperationalActivity.photos), selectinload(OperationalActivity.attachments))
    return query


def actor_name(user): return ' '.join(filter(None,[getattr(user,'name',''),getattr(user,'surname','')])) if user else 'Utente non disponibile'


def activity_data(row, user, detail=False):
    arrival = row.arrival
    active_role_ids = {role.id for role in user.active_roles}
    minimum_role_weight = row.target_min_role.weight if row.target_min_role else row.target_min_weight
    assigned = row.owner_id == user.id or any(t.role_id in active_role_ids for t in row.targets) or any(t.user_id == user.id for t in row.user_targets)
    result_weight = row.result_min_role.weight if row.result_min_role else row.result_min_weight
    result_recipient = any(t.user_id == user.id for t in row.result_users) or any(t.role_id in active_role_ids for t in row.result_roles) or (result_weight is not None and result_weight <= (user.max_role_weight or 0))
    executor = sees_all(user) or assigned or (row.status in CLOSED and result_recipient) or (minimum_role_weight is not None and minimum_role_weight <= (user.max_role_weight or 0))
    editable=can_edit(row,user)
    data = dict(id=row.id,title=row.title,kind=row.kind,status=row.status,revision=row.revision,cycle=row.cycle,
        parent_id=row.parent_id,can_edit=editable,
        can_create_child=(executor or editable) and row.status in ACTIVE and (not row.owner_id or row.owner_id==user.id or manager(user)),
        description=row.description,users=[dict(id=target.user_id,name=actor_name(target.user)) for target in row.user_targets if target.user],
        target_min_weight=(row.target_min_role.weight if row.target_min_role else row.target_min_weight),target_min_role_id=row.target_min_role_id,
        result_recipients=dict(roles=[t.role.name for t in row.result_roles if t.role], users=[dict(id=t.user_id,name=actor_name(t.user)) for t in row.result_users if t.user], target_min_weight=(row.result_min_role.weight if row.result_min_role else row.result_min_weight),target_min_role_id=row.result_min_role_id),
        owner_id=row.owner_id,owner=actor_name(row.owner) if row.owner_id else None,
        roles=[target.role.name for target in row.targets if target.role], created_at=row.created_at.isoformat(),
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        can_manage=editable,can_act=(sees_all(user) or assigned or (minimum_role_weight is not None and minimum_role_weight <= (user.max_role_weight or 0)) or editable) and row.status in ACTIVE and (not row.owner_id or row.owner_id==user.id or manager(user)),
        source=dict(id=arrival.id,label=arrival.label,reference=arrival.reference,received_on=arrival.received_on.isoformat(),
                    partial=arrival.partial,note=arrival.note,card_id=arrival.card_id) if arrival else None)
    if detail:
        data['role_ids'] = [t.role_id for t in row.targets]
        data['result_recipients']['role_ids'] = [t.role_id for t in row.result_roles]
        child_rows=visible_query(user,include_results=True).filter_by(parent_id=row.id).order_by(OperationalActivity.completed_at.desc(),OperationalActivity.id).all()
        data['children']=[dict(id=c.id,title=c.title,status=c.status,completed_at=c.completed_at.isoformat() if c.completed_at else None) for c in child_rows]
        data['blocked_children']=OperationalActivity.query.filter_by(parent_id=row.id).filter(~OperationalActivity.status.in_(('completed','not_required'))).count()
        data['parent_visible']=bool(row.parent_id and visible_query(user,include_results=True).filter_by(id=row.parent_id).first())
        data['attachments'] = [dict(id=f.id,filename=f.filename,mimetype=f.mimetype,size=f.size,cycle=f.cycle,purpose=f.purpose,url=f'/activities/api/attachments/{f.id}') for f in row.attachments]
        data['events'] = [dict(id=event.id,action=event.action,note=event.note,actor=actor_name(event.actor),created_at=event.created_at.isoformat()) for event in row.events]
        data['photos'] = [dict(id=photo.id,label=photo.label,cycle=photo.cycle,url=f'/activities/api/photos/{photo.id}') for photo in row.photos]
    return data


def routing_data():
    pref = AppPreference.query.filter_by(key=CONFIG_KEY).first()
    stored = pref.value_json if pref and isinstance(pref.value_json,dict) else {}
    roles = Role.query.filter(Role.weight >= resolve_minimum_weight("staff")).order_by(Role.weight,Role.name).all()
    defaults = [role.id for role in roles if str(role.name or '').strip().lower()=='staff']
    rules = stored.get('rules') or {kind:defaults for kind in KINDS}
    return dict(revision=stored.get('revision',0),rules=rules,
        roles=[dict(id=role.id,name=role.name) for role in roles],kinds=KINDS)


def operational_users():
    now = datetime.now()
    return User.query.join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id).filter(
        Role.weight >= resolve_minimum_weight("staff"), (UserRole.valid_from.is_(None) | (UserRole.valid_from <= now)),
        (UserRole.valid_until.is_(None) | (UserRole.valid_until >= now))).distinct()


def manual_payload(payload):
    import re
    if not isinstance(payload, dict): raise ValueError('Dati non validi.')
    title, description, key = payload.get('title'), payload.get('description', ''), payload.get('client_key')
    if not isinstance(title, str) or not title.strip() or len(title) > 200: raise ValueError('Inserisci un titolo di massimo 200 caratteri.')
    if not isinstance(description, str) or len(description) > 5000: raise ValueError('Descrizione: massimo 5.000 caratteri.')
    if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}', key): raise ValueError('Identificativo richiesta non valido.')
    targets = []
    for field in ('role_ids', 'user_ids'):
        values = payload.get(field, [])
        if not isinstance(values, list) or len(values) > 200 or any(type(value) is not int for value in values): raise ValueError('Destinatari non validi.')
        targets.append(sorted(set(values)))
    roles, users = targets
    valid_minimum_weights = {role.weight for role in Role.query.filter(Role.weight >= resolve_minimum_weight("staff")).all()}
    weight = payload.get('target_min_weight')
    if weight is not None and (type(weight) is not int or weight not in valid_minimum_weights):
        raise ValueError('Scegli un ruolo minimo operativo uguale o superiore a staff.')
    if not roles and not users and weight is None: raise ValueError('Scegli almeno un utente, ruolo o peso minimo.')
    result = payload.get('result_recipients')
    if result is None: raise ValueError('Scegli i destinatari dell’esito.')
    if not isinstance(result, dict): raise ValueError('Destinatari esito non validi.')
    normalized = {}
    for field in ('role_ids', 'user_ids'):
        values = result.get(field, [])
        if not isinstance(values, list) or len(values)>200 or any(type(v) is not int for v in values): raise ValueError('Destinatari esito non validi.')
        normalized[field] = sorted(set(values))
    minimum = result.get('target_min_weight')
    if minimum is not None and (type(minimum) is not int or minimum not in valid_minimum_weights): raise ValueError('Soglia minima esito non valida.')
    normalized['target_min_weight'] = minimum
    if 'result_recipients' in payload and not normalized['role_ids'] and not normalized['user_ids'] and minimum is None:
        raise ValueError('Scegli almeno un destinatario dell’esito.')
    target_role_id=payload.get('target_min_role_id')
    if target_role_id is not None:
        target_role=Role.query.filter_by(id=target_role_id).first() if type(target_role_id) is int else None
        if not target_role or target_role.weight < resolve_minimum_weight('staff'): raise ValueError('Scegli un ruolo minimo operativo uguale o superiore a staff.')
    result_role_id=result.get('target_min_role_id')
    if result_role_id is not None:
        result_role=Role.query.filter_by(id=result_role_id).first() if type(result_role_id) is int else None
        if not result_role or result_role.weight < resolve_minimum_weight('staff'): raise ValueError('Soglia minima esito non valida.')
    return dict(title=title.strip(), description=description.strip(), client_key=key, role_ids=roles, user_ids=users, target_min_weight=weight, target_min_role_id=target_role_id, result_recipients={**normalized,'target_min_role_id':result_role_id})


def manual_matches(row, payload):
    return row.title == payload['title'] and row.description == payload['description'] and sorted(t.role_id for t in row.targets) == payload['role_ids'] and sorted(t.user_id for t in row.user_targets) == payload['user_ids'] and row.target_min_weight == payload['target_min_weight'] and sorted(t.role_id for t in row.result_roles) == payload['result_recipients']['role_ids'] and sorted(t.user_id for t in row.result_users) == payload['result_recipients']['user_ids'] and row.result_min_weight == payload['result_recipients']['target_min_weight'] and row.creation_files_digest == payload.get('files_digest') and row.parent_id == payload.get('parent_id')


def validate_manual_targets(payload):
    result = payload['result_recipients']
    roles = sorted(set(payload['role_ids'] + result['role_ids']))
    users = sorted(set(payload['user_ids'] + result['user_ids']))
    valid_roles = {role.id for role in Role.query.filter(Role.weight >= resolve_minimum_weight("staff"), Role.id.in_(roles)).all()}
    valid_users = {row.id for row in operational_users().filter(User.id.in_(users)).all()}
    if set(roles) != valid_roles or set(users) != valid_users: raise ValueError('Scegli ruoli e utenti operativi attivi. Aggiorna i destinatari.')


def supplier_arrival_activity_specs(payload):
    """Validate the selected arrival tasks and their assignee/result audiences."""
    if 'activities' not in payload:
        return None
    raw_specs = payload.get('activities')
    if not isinstance(raw_specs, list) or not raw_specs or len(raw_specs) > len(KINDS):
        raise ValueError('Seleziona almeno un’attività da inviare.')
    result = []
    seen = set()
    for raw in raw_specs:
        if not isinstance(raw, dict) or raw.get('kind') not in KINDS or raw['kind'] in seen:
            raise ValueError('Selezione attività non valida.')
        kind = raw['kind']
        seen.add(kind)
        normalized = manual_payload({
            'title': KINDS[kind],
            'description': '',
            'client_key': f"{str(payload.get('event_key') or '')[:50]}-{kind}",
            'role_ids': raw.get('role_ids', []),
            'user_ids': raw.get('user_ids', []),
            'target_min_weight': raw.get('target_min_weight'),
            'result_recipients': raw.get('result_recipients'),
        })
        validate_manual_targets(normalized)
        result.append(dict(kind=kind, role_ids=normalized['role_ids'], user_ids=normalized['user_ids'],
                           target_min_weight=normalized['target_min_weight'],
                           result_recipients=normalized['result_recipients']))
    return result


def create_manual(payload, user):
    validate_manual_targets(payload)
    result=payload['result_recipients']
    target_role=db.session.get(Role,payload.get('target_min_role_id')) if payload.get('target_min_role_id') is not None else (Role.query.filter_by(weight=payload['target_min_weight']).order_by(Role.id).first() if payload['target_min_weight'] is not None else None)
    row = OperationalActivity(parent_id=payload.get('parent_id'),kind='manual', title=payload['title'], description=payload['description'], client_key=payload['client_key'], target_min_weight=payload['target_min_weight'],target_min_role=target_role)
    row.targets = [ActivityTargetRole(role_id=value) for value in payload['role_ids']]
    row.user_targets = [ActivityTargetUser(user_id=value) for value in payload['user_ids']]
    row.result_roles = [ActivityResultRole(role_id=value) for value in result['role_ids']]
    row.result_users = [ActivityResultUser(user_id=value) for value in result['user_ids']]
    result_role=db.session.get(Role,result.get('target_min_role_id')) if result.get('target_min_role_id') is not None else (Role.query.filter_by(weight=result['target_min_weight']).order_by(Role.id).first() if result['target_min_weight'] is not None else None)
    row.result_min_weight = result['target_min_weight'];row.result_min_role=result_role
    row.creation_files_digest = payload.get('files_digest')
    add_event(row, user, 'created')
    db.session.add(row)
    return row


def validate_rules(payload):
    if not isinstance(payload,dict) or type(payload.get('revision')) is not int or not isinstance(payload.get('rules'),dict):
        raise ValueError('Configurazione non valida.')
    if set(payload['rules']) != set(KINDS): raise ValueError('Configura i destinatari delle tre attività.')
    valid = {role.id for role in Role.query.filter(Role.weight>=resolve_minimum_weight("staff")).all()}
    rules = {}
    for kind,title in KINDS.items():
        ids = payload['rules'][kind]
        if not isinstance(ids,list) or not ids or len(ids)>30 or any(type(value) is not int or value not in valid for value in ids):
            raise ValueError(f'Scegli almeno un ruolo operativo valido per «{title}».')
        rules[kind] = sorted(set(ids))
    return rules


def add_event(row, user, action, note=''):
    event=ActivityEvent(actor_id=user.id,action=action,note=note)
    row.events.append(event)
    # Notices share the action transaction; do not flush before idempotency checks.
    create_result_notices(row)
    if has_request_context(): g.activity_notifications=True


def transition(row, user, action, note):
    if not isinstance(note,str) or len(note)>2000: raise ValueError('Inserisci una nota di massimo 2.000 caratteri.')
    note = note.strip()
    if action in ('reopen','cancel') and not manager(user): raise PermissionError('Operazione riservata all’ufficio.')
    if action not in ('reopen','cancel') and row.owner_id and row.owner_id != user.id and not manager(user):
        raise PermissionError('L’attività è già in carico a un’altra persona.')
    if action=='reopen' and row.parent_id and db.session.get(OperationalActivity,row.parent_id).status in CLOSED:
        raise ValueError('Riapri prima l’attività principale.')
    if action in ('complete','not_required') and OperationalActivity.query.filter_by(parent_id=row.id).filter(~OperationalActivity.status.in_(('completed','not_required'))).first():
        raise ValueError('Attendi gli esiti di tutte le sottoattività prima di completare questa attività.')
    if action=='reopen':
        if row.status not in CLOSED or not note: raise ValueError('Motiva la riapertura di un’attività chiusa.')
        row.status='pending';row.owner_id=None;row.completed_at=None;row.cycle+=1
    elif action=='cancel':
        if row.status not in ACTIVE or not note: raise ValueError('Motiva l’annullamento di un’attività aperta.')
        row.status='cancelled';row.completed_at=datetime.utcnow()
    else:
        if row.status not in ACTIVE: raise ValueError('L’attività è già chiusa.')
        if action=='claim':
            if row.status!='pending': raise ValueError('L’attività è già in corso.')
            row.owner_id=user.id;row.status='in_progress'
        elif action=='release':
            if row.status!='in_progress': raise ValueError('L’attività non è in carico.')
            row.owner_id=None;row.status='pending'
        elif action in ('complete','not_required'):
            if action=='not_required' and (row.kind!='lots' or not note): raise ValueError('Motiva perché i lotti non sono necessari.')
            if action=='complete' and row.kind=='lots' and not ActivityPhoto.query.filter_by(activity_id=row.id,cycle=row.cycle).first() and not ActivityAttachment.query.filter_by(activity_id=row.id,cycle=row.cycle,purpose='result').filter(ActivityAttachment.mimetype.like('image/%')).first():
                raise ValueError('Allega le foto dei lotti oppure scegli Non necessario con una motivazione.')
            row.owner_id=user.id;row.status='completed' if action=='complete' else 'not_required';row.completed_at=datetime.utcnow()
        else: raise ValueError('Azione non valida.')
    row.revision+=1;add_event(row,user,action,note)
    logger.info('Activity action id=%s action=%s actor=%s cycle=%s', row.id, action, user.id, row.cycle)


def create_arrival(card, payload, user, received_on):
    specs = payload.get('_activity_specs')
    if specs is None:
        routing = routing_data()
        rules = routing['rules']
        valid = {role['id'] for role in routing['roles']}
        if any(not rules.get(kind) or not set(rules[kind]) <= valid for kind in KINDS):
            raise ValueError('Configura prima i ruoli destinatari nell’area Attività.')
        office_role=Role.query.filter(Role.name.ilike('office')).first()
        specs = [dict(kind=kind, role_ids=sorted(set(rules[kind])), user_ids=[], target_min_weight=None,
                      target_min_role_id=None, result_recipients=dict(role_ids=[], user_ids=[], target_min_weight=office_role.weight if office_role else resolve_minimum_weight('office'),result_min_role_id=office_role.id if office_role else None))
                 for kind in KINDS]
    arrival = SupplierArrival(event_key=payload['event_key'],card_id=card.id,label=card.title,reference=card.reference or '',
        received_on=received_on,partial=payload['partial'],note=payload['note'],created_by_id=user.id)
    db.session.add(arrival);db.session.flush()
    for spec in specs:
        kind=spec['kind']
        recipients=spec['result_recipients']
        row=OperationalActivity(arrival_id=arrival.id,kind=kind,title=KINDS[kind],status='pending',revision=1,cycle=1,
            target_min_weight=spec['target_min_weight'],result_min_weight=recipients['target_min_weight'],
            target_min_role_id=spec.get('target_min_role_id'),result_min_role_id=recipients.get('result_min_role_id'))
        row.targets=[ActivityTargetRole(role_id=role_id) for role_id in spec['role_ids']]
        row.user_targets=[ActivityTargetUser(user_id=user_id) for user_id in spec['user_ids']]
        row.result_roles=[ActivityResultRole(role_id=role_id) for role_id in recipients['role_ids']]
        row.result_users=[ActivityResultUser(user_id=user_id) for user_id in recipients['user_ids']]
        add_event(row,user,'created',arrival.note);db.session.add(row)
    return arrival


def notification_recipients(row):
    """Snapshot assignees, outcome recipients and the direct parent's assignees."""
    role_ids={t.role_id for t in row.targets} | {t.role_id for t in row.result_roles}
    user_ids={t.user_id for t in row.user_targets} | {t.user_id for t in row.result_users}
    weights=[w for w in (row.target_min_role.weight if row.target_min_role else row.target_min_weight,row.result_min_role.weight if row.result_min_role else row.result_min_weight) if w is not None]
    parent=db.session.get(OperationalActivity,row.parent_id) if row.parent_id else None
    if parent:
        role_ids.update(t.role_id for t in parent.targets)
        user_ids.update(t.user_id for t in parent.user_targets)
        parent_weight=parent.target_min_role.weight if parent.target_min_role else parent.target_min_weight
        if parent_weight is not None: weights.append(parent_weight)
    now=datetime.now()
    memberships=db.session.query(UserRole.user_id,UserRole.role_id,Role.weight).join(Role).filter(
        (UserRole.valid_from.is_(None) | (UserRole.valid_from<=now)),
        (UserRole.valid_until.is_(None) | (UserRole.valid_until>=now))).all()
    user_ids.update(uid for uid,rid,weight in memberships if rid in role_ids or any(weight>=w for w in weights))
    return user_ids


def create_result_notices(row, extra_user_ids=()):
    """One durable notification per recipient and event, committed with the action."""
    with db.session.no_autoflush:
        event=row.events[-1]
        recipients=notification_recipients(row) | set(extra_user_ids)
        existing={n.user_id for n in row.result_notices if n.event is event or (event.id is not None and n.event_id==event.id)}
        for uid in recipients-existing:
            row.result_notices.append(ActivityResultNotice(event=event,user_id=uid,cycle=row.cycle or 1))
    logger.info('Activity event notice activity=%s action=%s recipients=%s',row.id,event.action,len(recipients))


def notices_query(user):
    return ActivityResultNotice.query.join(OperationalActivity).filter(
        ActivityResultNotice.user_id == user.id)


def notices_data(user, limit=30):
    query=notices_query(user).filter(ActivityResultNotice.read_at.is_(None))
    notices=query.options(selectinload(ActivityResultNotice.activity),
        selectinload(ActivityResultNotice.event).selectinload(ActivityEvent.actor)).order_by(ActivityResultNotice.id.desc()).limit(limit).all()
    readable={i for i, in visible_query(user,include_results=True).filter(OperationalActivity.id.in_({n.activity_id for n in notices})).with_entities(OperationalActivity.id).all()}
    return dict(count=query.count(),rows=[dict(id=n.id,activity_id=n.activity_id,title=n.activity.title,
        can_open=n.activity_id in readable,cycle=n.cycle,status=n.activity.status,action=n.event.action,
        actor=actor_name(n.event.actor),note=n.event.note,message=event_message(n.event),created_at=n.event.created_at.isoformat()) for n in notices])


def badge_count(user):
    """Open assigned activities plus unread event notifications, using the same visibility rules."""
    return (visible_query(user).filter(OperationalActivity.status.in_(ACTIVE)).count()
            + notices_query(user).filter(ActivityResultNotice.read_at.is_(None)).count())


EVENT_LABELS = {'created':'Attività creata','claim':'Presa in carico','release':'Attività rilasciata',
    'complete':'Attività completata','not_required':'Non necessario','cancel':'Attività annullata',
    'reopen':'Attività riaperta','updated':'Attività modificata','child_created':'Sottoattività creata',
    'linked':'Collegamento alla principale','photo_added':'Foto aggiunta','photo_removed':'Foto rimossa',
    'files_added':'Allegati aggiunti','file_removed':'Allegato rimosso'}


def event_message(event):
    label=EVENT_LABELS.get(event.action,event.action)
    return label+' · '+actor_name(event.actor)+((' · '+event.note) if event.note else '')

"""Shared operational work, role visibility and supplier-arrival workflows."""
from datetime import datetime
from flask import current_app
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from extensions import db
from models import (AppPreference, Role, User, UserRole, OperationalActivity, ActivityTargetRole, ActivityTargetUser,
                    ActivityEvent, ActivityPhoto, SupplierArrival, ActivityResultRole, ActivityResultUser, ActivityAttachment, ActivityResultNotice)

KINDS = {'check_goods':'Controllare la merce', 'lots':'Inviare i lotti', 'store_goods':'Sistemare i prodotti in magazzino'}
ACTIVE = ('pending','in_progress')
CLOSED = ('completed','not_required','cancelled')
from tools.log_utils import get_logger
logger = get_logger('activities')

CONFIG_KEY = 'activities.supplier_arrival.routing'


def manager(user): return (user.max_role_weight or 0) >= 40


def sees_all(user):
    """Admin (900) and Dev (1000); office management alone grants no visibility."""
    return (user.max_role_weight or 0) >= 900


def visible_query(user, include_results=False):
    query = OperationalActivity.query
    if not sees_all(user):
        ids = [role.id for role in user.active_roles]
        query = query.filter(db.session.query(ActivityTargetRole.activity_id).filter(
            ActivityTargetRole.activity_id == OperationalActivity.id,
            ActivityTargetRole.role_id.in_(ids)).exists() | db.session.query(ActivityTargetUser.activity_id).filter(
            ActivityTargetUser.activity_id == OperationalActivity.id, ActivityTargetUser.user_id == user.id).exists() |
            (OperationalActivity.target_min_weight.isnot(None) &
             (OperationalActivity.target_min_weight <= (user.max_role_weight or 0))))
    if include_results and not sees_all(user):
        return OperationalActivity.query.filter(OperationalActivity.id.in_(query.with_entities(OperationalActivity.id)) | result_access(user))
    return query


def result_access(user):
    return OperationalActivity.status.in_(CLOSED) & db.session.query(ActivityResultNotice.id).filter(
        ActivityResultNotice.activity_id == OperationalActivity.id,
        ActivityResultNotice.user_id == user.id, ActivityResultNotice.cycle == OperationalActivity.cycle).exists()


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
    executor = sees_all(user) or any(t.role_id in active_role_ids for t in row.targets) or any(t.user_id == user.id for t in row.user_targets) or (row.target_min_weight is not None and row.target_min_weight <= (user.max_role_weight or 0))
    data = dict(id=row.id,title=row.title,kind=row.kind,status=row.status,revision=row.revision,cycle=row.cycle,
        description=row.description,users=[dict(id=target.user_id,name=actor_name(target.user)) for target in row.user_targets if target.user],
        target_min_weight=row.target_min_weight,
        result_recipients=dict(roles=[t.role.name for t in row.result_roles if t.role], users=[dict(id=t.user_id,name=actor_name(t.user)) for t in row.result_users if t.user], target_min_weight=row.result_min_weight),
        owner_id=row.owner_id,owner=actor_name(row.owner) if row.owner_id else None,
        roles=[target.role.name for target in row.targets if target.role], created_at=row.created_at.isoformat(),
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        can_manage=executor and manager(user),can_act=executor and (not row.owner_id or row.owner_id==user.id or manager(user)),
        source=dict(id=arrival.id,label=arrival.label,reference=arrival.reference,received_on=arrival.received_on.isoformat(),
                    partial=arrival.partial,note=arrival.note,card_id=arrival.card_id) if arrival else None)
    if detail:
        data['attachments'] = [dict(id=f.id,filename=f.filename,mimetype=f.mimetype,size=f.size,cycle=f.cycle,purpose=f.purpose,url=f'/activities/api/attachments/{f.id}') for f in row.attachments]
        data['events'] = [dict(id=event.id,action=event.action,note=event.note,actor=actor_name(event.actor),created_at=event.created_at.isoformat()) for event in row.events]
        data['photos'] = [dict(id=photo.id,label=photo.label,cycle=photo.cycle,url=f'/activities/api/photos/{photo.id}') for photo in row.photos]
    return data


def routing_data():
    pref = AppPreference.query.filter_by(key=CONFIG_KEY).first()
    stored = pref.value_json if pref and isinstance(pref.value_json,dict) else {}
    roles = Role.query.filter(Role.weight >= 30).order_by(Role.weight,Role.name).all()
    defaults = [role.id for role in roles if str(role.name or '').strip().lower()=='staff']
    rules = stored.get('rules') or {kind:defaults for kind in KINDS}
    return dict(revision=stored.get('revision',0),rules=rules,
        roles=[dict(id=role.id,name=role.name) for role in roles],kinds=KINDS)


def operational_users():
    now = datetime.now()
    return User.query.join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id).filter(
        Role.weight >= 30, (UserRole.valid_from.is_(None) | (UserRole.valid_from <= now)),
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
    weight = payload.get('target_min_weight')
    if weight is not None and (type(weight) is not int or not 30 <= weight <= 1000):
        raise ValueError('Scegli un peso minimo operativo da 30 a 1000.')
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
    if minimum is not None and (type(minimum) is not int or not 30 <= minimum <= 1000): raise ValueError('Peso minimo esito non valido.')
    normalized['target_min_weight'] = minimum
    if 'result_recipients' in payload and not normalized['role_ids'] and not normalized['user_ids'] and minimum is None:
        raise ValueError('Scegli almeno un destinatario dell’esito.')
    return dict(title=title.strip(), description=description.strip(), client_key=key, role_ids=roles, user_ids=users, target_min_weight=weight, result_recipients=normalized)


def manual_matches(row, payload):
    return row.title == payload['title'] and row.description == payload['description'] and sorted(t.role_id for t in row.targets) == payload['role_ids'] and sorted(t.user_id for t in row.user_targets) == payload['user_ids'] and row.target_min_weight == payload['target_min_weight'] and sorted(t.role_id for t in row.result_roles) == payload['result_recipients']['role_ids'] and sorted(t.user_id for t in row.result_users) == payload['result_recipients']['user_ids'] and row.result_min_weight == payload['result_recipients']['target_min_weight'] and row.creation_files_digest == payload.get('files_digest')


def create_manual(payload, user):
    result = payload['result_recipients']
    roles = sorted(set(payload['role_ids'] + result['role_ids']))
    users = sorted(set(payload['user_ids'] + result['user_ids']))
    valid_roles = {role.id for role in Role.query.filter(Role.weight >= 30, Role.id.in_(roles)).all()}
    valid_users = {row.id for row in operational_users().filter(User.id.in_(users)).all()}
    if set(roles) != valid_roles or set(users) != valid_users: raise ValueError('Scegli ruoli e utenti operativi attivi. Aggiorna i destinatari.')
    row = OperationalActivity(kind='manual', title=payload['title'], description=payload['description'], client_key=payload['client_key'], target_min_weight=payload['target_min_weight'])
    row.targets = [ActivityTargetRole(role_id=value) for value in payload['role_ids']]
    row.user_targets = [ActivityTargetUser(user_id=value) for value in payload['user_ids']]
    row.result_roles = [ActivityResultRole(role_id=value) for value in result['role_ids']]
    row.result_users = [ActivityResultUser(user_id=value) for value in result['user_ids']]
    row.result_min_weight = result['target_min_weight']
    row.creation_files_digest = payload.get('files_digest')
    add_event(row, user, 'created')
    db.session.add(row)
    return row


def validate_rules(payload):
    if not isinstance(payload,dict) or type(payload.get('revision')) is not int or not isinstance(payload.get('rules'),dict):
        raise ValueError('Configurazione non valida.')
    if set(payload['rules']) != set(KINDS): raise ValueError('Configura i destinatari delle tre attività.')
    valid = {role.id for role in Role.query.filter(Role.weight>=30).all()}
    rules = {}
    for kind,title in KINDS.items():
        ids = payload['rules'][kind]
        if not isinstance(ids,list) or not ids or len(ids)>30 or any(type(value) is not int or value not in valid for value in ids):
            raise ValueError(f'Scegli almeno un ruolo operativo valido per «{title}».')
        rules[kind] = sorted(set(ids))
    return rules


def add_event(row, user, action, note=''):
    row.events.append(ActivityEvent(actor_id=user.id,action=action,note=note))


def transition(row, user, action, note):
    if not isinstance(note,str) or len(note)>2000: raise ValueError('Inserisci una nota di massimo 2.000 caratteri.')
    note = note.strip()
    if action in ('reopen','cancel') and not manager(user): raise PermissionError('Operazione riservata all’ufficio.')
    if action not in ('reopen','cancel') and row.owner_id and row.owner_id != user.id and not manager(user):
        raise PermissionError('L’attività è già in carico a un’altra persona.')
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
    if action in ('complete','not_required','cancel'): create_result_notices(row)
    logger.info('Activity action id=%s action=%s actor=%s cycle=%s', row.id, action, user.id, row.cycle)


def create_arrival(card, payload, user, received_on):
    routing = routing_data()
    rules = routing['rules']
    valid = {role['id'] for role in routing['roles']}
    if any(not rules.get(kind) or not set(rules[kind]) <= valid for kind in KINDS):
        raise ValueError('Configura prima i ruoli destinatari nell’area Attività.')
    arrival = SupplierArrival(event_key=payload['event_key'],card_id=card.id,label=card.title,reference=card.reference or '',
        received_on=received_on,partial=payload['partial'],note=payload['note'],created_by_id=user.id)
    db.session.add(arrival);db.session.flush()
    for kind,title in KINDS.items():
        row=OperationalActivity(arrival_id=arrival.id,kind=kind,title=title,status='pending',revision=1,cycle=1)
        row.targets=[ActivityTargetRole(role_id=role_id) for role_id in set(rules[kind])]
        add_event(row,user,'created',arrival.note);db.session.add(row)
    return arrival


def create_result_notices(row):
    """Resolve exact roles, explicit users and minimum weight at completion."""
    db.session.flush()
    role_ids = {t.role_id for t in row.result_roles}
    user_ids = {t.user_id for t in row.result_users}
    now = datetime.now()
    memberships = db.session.query(UserRole.user_id, UserRole.role_id, Role.weight).join(Role).filter(
        (UserRole.valid_from.is_(None) | (UserRole.valid_from <= now)),
        (UserRole.valid_until.is_(None) | (UserRole.valid_until >= now))).all()
    user_ids.update(uid for uid, rid, weight in memberships if rid in role_ids or (row.result_min_weight is not None and weight >= row.result_min_weight))
    for uid in user_ids:
        db.session.add(ActivityResultNotice(activity_id=row.id,event_id=row.events[-1].id,user_id=uid,cycle=row.cycle))
    logger.info('Activity result id=%s event=%s recipients=%s', row.id, row.events[-1].id, len(user_ids))


def notices_query(user):
    return ActivityResultNotice.query.join(OperationalActivity).filter(
        ActivityResultNotice.user_id == user.id, ActivityResultNotice.cycle == OperationalActivity.cycle,
        OperationalActivity.status.in_(CLOSED))


def notices_data(user, limit=30):
    query = notices_query(user).filter(ActivityResultNotice.read_at.is_(None))
    return dict(count=query.count(), rows=[dict(id=n.id,activity_id=n.activity_id,title=n.activity.title,
        status=n.activity.status,note=n.event.note,created_at=n.event.created_at.isoformat())
        for n in query.options(selectinload(ActivityResultNotice.activity),selectinload(ActivityResultNotice.event))
        .order_by(ActivityResultNotice.id.desc()).limit(limit).all()])

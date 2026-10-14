"""Shared operational work, role visibility and supplier-arrival workflows."""
from datetime import datetime
from flask import current_app
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from extensions import db
from models import (AppPreference, Role, OperationalActivity, ActivityTargetRole,
                    ActivityEvent, ActivityPhoto, SupplierArrival)

KINDS = {'check_goods':'Controllare la merce', 'lots':'Inviare i lotti', 'store_goods':'Sistemare i prodotti in magazzino'}
ACTIVE = ('pending','in_progress')
CLOSED = ('completed','not_required','cancelled')
CONFIG_KEY = 'activities.supplier_arrival.routing'


def manager(user): return (user.max_role_weight or 0) >= 40


def visible_query(user):
    query = OperationalActivity.query
    if not manager(user):
        ids = [role.id for role in user.active_roles]
        query = query.filter(db.session.query(ActivityTargetRole.activity_id).filter(
            ActivityTargetRole.activity_id == OperationalActivity.id,
            ActivityTargetRole.role_id.in_(ids)).exists())
    return query


def activity_query(user, detail=False):
    query = visible_query(user).options(selectinload(OperationalActivity.arrival), selectinload(OperationalActivity.owner),
        selectinload(OperationalActivity.targets).selectinload(ActivityTargetRole.role))
    if detail:
        query = query.options(selectinload(OperationalActivity.events).selectinload(ActivityEvent.actor), selectinload(OperationalActivity.photos))
    return query


def actor_name(user): return ' '.join(filter(None,[getattr(user,'name',''),getattr(user,'surname','')])) if user else 'Utente non disponibile'


def activity_data(row, user, detail=False):
    arrival = row.arrival
    data = dict(id=row.id,title=row.title,kind=row.kind,status=row.status,revision=row.revision,cycle=row.cycle,
        owner_id=row.owner_id,owner=actor_name(row.owner) if row.owner_id else None,
        roles=[target.role.name for target in row.targets if target.role], created_at=row.created_at.isoformat(),
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        can_manage=manager(user),can_act=not row.owner_id or row.owner_id==user.id or manager(user),
        source=dict(id=arrival.id,label=arrival.label,reference=arrival.reference,received_on=arrival.received_on.isoformat(),
                    partial=arrival.partial,note=arrival.note,card_id=arrival.card_id) if arrival else None)
    if detail:
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
            if action=='complete' and row.kind=='lots' and not ActivityPhoto.query.filter_by(activity_id=row.id,cycle=row.cycle).first():
                raise ValueError('Allega le foto dei lotti oppure scegli Non necessario con una motivazione.')
            row.owner_id=user.id;row.status='completed' if action=='complete' else 'not_required';row.completed_at=datetime.utcnow()
        else: raise ValueError('Azione non valida.')
    row.revision+=1;add_event(row,user,action,note)


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

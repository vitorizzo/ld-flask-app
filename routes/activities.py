from datetime import date
import re
from flask import Blueprint, jsonify, render_template, request, send_file, abort
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from extensions import db
from models import (AppPreference, OperationalActivity, ActivityPhoto, SupplierArrival, SupplierBoardCard)
from tools.activities import (ACTIVE,CLOSED,CONFIG_KEY,manager,visible_query,activity_query,activity_data,
                              routing_data,validate_rules,transition,create_arrival,add_event)
from tools.activity_photos import store_photo, photo_path

activities_bp=Blueprint('activities',__name__)


def office():
    if not manager(current_user): abort(403)


def error(message,status=400): return jsonify(ok=False,error=message),status


def locked_activity(activity_id,revision):
    row=visible_query(current_user).filter_by(id=activity_id).with_for_update().first()
    if row is None: abort(404)
    if type(revision) is not int or revision!=row.revision: return row,error('L’attività è cambiata. Aggiorna il dettaglio.',409)
    return row,None


@activities_bp.get('')
@login_required
def index(): return render_template('activities/index.html',activity_manager=manager(current_user))


@activities_bp.get('/api')
@login_required
def activity_list():
    try: page=int(request.args.get('page','1'))
    except ValueError: return error('Pagina non valida.')
    if not 1 <= page <= 100000: return error('Pagina non valida.')
    status=request.args.get('status','active');query=activity_query(current_user)
    statuses={'active':ACTIVE,'pending':('pending',),'in_progress':('in_progress',),'completed':('completed','not_required'),'cancelled':('cancelled',),'all':ACTIVE+CLOSED}
    if status not in statuses: return error('Filtro non valido.')
    query=query.filter(OperationalActivity.status.in_(statuses[status]))
    search=(request.args.get('q') or '').strip()[:120]
    if search:
        query=query.join(SupplierArrival).filter(SupplierArrival.label.ilike('%'+search+'%')|SupplierArrival.reference.ilike('%'+search+'%'))
    if request.args.get('arrival'):
        try: query=query.filter(OperationalActivity.arrival_id==int(request.args['arrival']))
        except ValueError: return error('Arrivo non valido.')
    total=query.count();rows=query.order_by(OperationalActivity.created_at,OperationalActivity.id).offset((page-1)*30).limit(30).all()
    counts=dict(visible_query(current_user).with_entities(OperationalActivity.status,func.count(OperationalActivity.id)).group_by(OperationalActivity.status).all())
    return jsonify(ok=True,rows=[activity_data(row,current_user) for row in rows],counts=counts,total=total,page=page,pages=(total+29)//30,manager=manager(current_user))


@activities_bp.get('/api/summary')
@login_required
def summary():
    query=activity_query(current_user).filter(OperationalActivity.status.in_(ACTIVE))
    return jsonify(ok=True,count=query.count(),rows=[activity_data(row,current_user) for row in query.order_by(OperationalActivity.created_at,OperationalActivity.id).limit(5).all()],manager=manager(current_user))


@activities_bp.get('/api/<int:activity_id>')
@login_required
def detail(activity_id):
    row=activity_query(current_user,True).filter_by(id=activity_id).first_or_404()
    return jsonify(ok=True,activity=activity_data(row,current_user,True))


@activities_bp.post('/api/<int:activity_id>/actions')
@login_required
def action(activity_id):
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return error('Dati non validi.')
    row,conflict=locked_activity(activity_id,payload.get('revision'))
    if conflict: return conflict
    try: transition(row,current_user,payload.get('action'),payload.get('note',''))
    except PermissionError as exc: return error(str(exc),403)
    except ValueError as exc: return error(str(exc))
    db.session.commit()
    return jsonify(ok=True,activity=activity_data(row,current_user,True))


@activities_bp.route('/api/routing',methods=['GET','PUT'])
@login_required
def routing():
    office()
    if request.method=='GET': return jsonify(ok=True,**routing_data())
    payload=request.get_json(silent=True)
    try: rules=validate_rules(payload)
    except ValueError as exc: return error(str(exc))
    row=AppPreference.query.filter_by(key=CONFIG_KEY).with_for_update().first()
    existing=row.value_json if row and isinstance(row.value_json,dict) else {}
    if payload['revision']!=existing.get('revision',0): return error('La configurazione è cambiata. Aggiornala.',409)
    if not row: row=AppPreference(key=CONFIG_KEY,category='Attività',label='Ruoli arrivi fornitori',value_type='json');db.session.add(row)
    row.value_json=dict(revision=payload['revision']+1,rules=rules)
    try: db.session.commit()
    except IntegrityError: db.session.rollback();return error('Configurazione aggiornata da un’altra persona. Riprova.',409)
    return jsonify(ok=True,**routing_data())


@activities_bp.get('/api/source-card/<int:card_id>')
@login_required
def source_card(card_id):
    office();card=db.session.get(SupplierBoardCard,card_id)
    if not card or card.is_archived or card.is_draft: abort(404)
    return jsonify(ok=True,card=dict(id=card.id,title=card.title,revision=card.order_revision))


@activities_bp.post('/api/supplier-arrivals')
@login_required
def arrival():
    office();payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return error('Dati arrivo non validi.')
    key=payload.get('event_key');card_id=payload.get('card_id');note=payload.get('note','');partial=payload.get('partial',False)
    if (not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',key) or type(card_id) is not int
        or not isinstance(note,str) or len(note)>2000 or type(partial) is not bool): return error('Dati arrivo non validi.')
    if partial and not note.strip(): return error('Indica i prodotti ricevuti nella consegna parziale.')
    try: received=date.fromisoformat(payload.get('received_on',''))
    except (ValueError,TypeError): return error('Data arrivo non valida.')
    def replay(existing):
        if existing.card_id!=card_id or existing.note!=note.strip() or existing.partial!=partial or existing.received_on!=received:
            return error('Il riferimento dell’arrivo è già usato per dati diversi.',409)
        return jsonify(ok=True,arrival_id=existing.id,replayed=True)
    # Serialize arrivals for the same card, then recheck the idempotency key.
    card=SupplierBoardCard.query.filter_by(id=card_id).with_for_update().first()
    existing=SupplierArrival.query.filter_by(event_key=key).first()
    if existing: return replay(existing)
    if not card or card.is_archived or card.is_draft: return error('Scheda non disponibile per un nuovo arrivo.',404)
    if type(payload.get('revision')) is not int or payload['revision']!=card.order_revision: return error('La scheda è cambiata. Riapri il nuovo arrivo.',409)
    body=dict(payload,event_key=key,note=note.strip(),partial=partial)
    try: result=create_arrival(card,body,current_user,received);db.session.commit()
    except ValueError as exc: db.session.rollback();return error(str(exc),409)
    except IntegrityError:
        db.session.rollback();existing=SupplierArrival.query.filter_by(event_key=key).first()
        return replay(existing) if existing else error('Arrivo non salvato. Riprova.',409)
    return jsonify(ok=True,arrival_id=result.id,replayed=False),201


@activities_bp.post('/api/<int:activity_id>/photos')
@login_required
def upload_photo(activity_id):
    # A cross-site HTML multipart form cannot add this non-safelisted header.
    if request.headers.get('X-Requested-With')!='XMLHttpRequest': return error('Carica le foto dall’area Attività.',403)
    try: revision=int(request.form.get('revision',''))
    except ValueError: return error('Revisione non valida.')
    row,conflict=locked_activity(activity_id,revision)
    if conflict: return conflict
    if row.kind!='lots' or row.status not in ACTIVE: return error('Foto ammesse solo nei lotti di un’attività aperta.')
    if row.owner_id and row.owner_id!=current_user.id and not manager(current_user): return error('L’attività è in carico a un’altra persona.',403)
    label=(request.form.get('label') or '').strip();upload=request.files.get('photo')
    if not label or len(label)>200 or upload is None: return error('Indica il prodotto e scegli una foto.')
    if ActivityPhoto.query.filter_by(activity_id=row.id,cycle=row.cycle).count()>=20: return error('Sono consentite al massimo 20 foto per questa lavorazione.')
    try: name=store_photo(upload)
    except ValueError as exc: return error(str(exc))
    try:
        if row.status=='pending': row.owner_id=current_user.id;row.status='in_progress';add_event(row,current_user,'claim')
        row.photos.append(ActivityPhoto(storage_name=name,cycle=row.cycle,label=label,actor_id=current_user.id));row.revision+=1
        add_event(row,current_user,'photo_added',label);db.session.commit()
    except SQLAlchemyError:
        db.session.rollback();photo_path(name).unlink(missing_ok=True);raise
    return jsonify(ok=True,activity=activity_data(row,current_user,True)),201


@activities_bp.get('/api/photos/<int:photo_id>')
@login_required
def photo(photo_id):
    item=db.session.get(ActivityPhoto,photo_id)
    if not item or not visible_query(current_user).filter_by(id=item.activity_id).first(): abort(404)
    path=photo_path(item.storage_name)
    if not path.is_file(): abort(404)
    response=send_file(path,mimetype='image/jpeg',max_age=0)
    response.headers['Cache-Control']='private, no-store';response.headers['X-Content-Type-Options']='nosniff'
    return response


@activities_bp.delete('/api/photos/<int:photo_id>')
@login_required
def delete_photo(photo_id):
    item=db.session.get(ActivityPhoto,photo_id)
    if not item: abort(404)
    payload=request.get_json(silent=True) or {}
    if not isinstance(payload,dict): return error('Dati foto non validi.')
    row,conflict=locked_activity(item.activity_id,payload.get('revision'))
    if conflict: return conflict
    if row.status not in ACTIVE or item.cycle!=row.cycle: return error('Le foto dello storico non possono essere rimosse.')
    if row.owner_id!=current_user.id and not manager(current_user): return error('Foto riservata alla persona incaricata.',403)
    name=item.storage_name;add_event(row,current_user,'photo_removed',item.label);db.session.delete(item);row.revision+=1;db.session.commit()
    photo_path(name).unlink(missing_ok=True);db.session.expire(row,['photos'])
    return jsonify(ok=True,activity=activity_data(row,current_user,True))

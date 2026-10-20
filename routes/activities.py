from datetime import date, datetime
from io import BytesIO
import json
import re
from flask import Blueprint, jsonify, render_template, request, send_file, abort, g
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from extensions import db
from tools.role_required import resolve_minimum_weight
from models import (AppPreference, OperationalActivity, ActivityPhoto, SupplierArrival, SupplierBoardCard,
                    SupplierBoardColumn, ActivityTargetRole, ActivityTargetUser, ActivityResultRole,
                    ActivityResultUser, Role, User, UserRole, ActivityAttachment, ActivityResultNotice)
from tools.activities import (ACTIVE,CLOSED,CONFIG_KEY,manager,visible_query,activity_query,activity_data,
                              routing_data,validate_rules,transition,create_arrival,add_event,
                              operational_users,actor_name,manual_payload,manual_matches,create_manual,sees_all,notices_data,notices_query,logger,lock_family,can_edit,
                              supplier_arrival_activity_specs)
from tools.activity_photos import store_photo, photo_path
from tools.activity_files import prepare_files, files_digest, attach_files

activities_bp=Blueprint('activities',__name__)


@activities_bp.after_request
def dispatch_event_notifications(response):
    pending=g.pop('activity_notifications',False)
    if response.status_code < 300 and pending:
        try:
            from tools.activity_results import enqueue_results
            enqueue_results()
        except Exception:
            logger.exception('Activity event enqueue failed; periodic dispatch will retry')
    return response


def office():
    if not manager(current_user): abort(403)


def error(message,status=400):
    logger.warning('Activity request rejected status=%s reason=%s',status,message)
    return jsonify(ok=False,error=message),status


def locked_activity(activity_id,revision):
    lock_family(activity_id)
    row=visible_query(current_user,include_results=manager(current_user)).filter_by(id=activity_id).populate_existing().with_for_update().first()
    if row is None or (not visible_query(current_user).filter_by(id=activity_id).first() and not can_edit(row,current_user)): abort(404)
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
        query=query.outerjoin(SupplierArrival).filter(SupplierArrival.label.ilike('%'+search+'%')|SupplierArrival.reference.ilike('%'+search+'%')|OperationalActivity.title.ilike('%'+search+'%')|OperationalActivity.description.ilike('%'+search+'%'))
    if request.args.get('arrival'):
        try: query=query.filter(OperationalActivity.arrival_id==int(request.args['arrival']))
        except ValueError: return error('Arrivo non valido.')
    matched={i for i, in query.with_entities(OperationalActivity.id).all()}
    parents=dict(visible_query(current_user,include_results=True).with_entities(OperationalActivity.id,OperationalActivity.parent_id).all())
    def root_id(i):
        visited=set()
        while parents.get(i) in parents and i not in visited:
            visited.add(i);i=parents[i]
        return i
    roots=sorted({root_id(i) for i in matched})
    total=len(roots);selected_roots=set(roots[(page-1)*30:page*30])
    ids=[i for i in parents if root_id(i) in selected_roots]
    rows=activity_query(current_user).filter(OperationalActivity.id.in_(ids)).order_by(OperationalActivity.created_at,OperationalActivity.id).all()
    counts=dict(visible_query(current_user).with_entities(OperationalActivity.status,func.count(OperationalActivity.id)).group_by(OperationalActivity.status).all())
    return jsonify(ok=True,rows=[activity_data(row,current_user) for row in rows],counts=counts,total=total,page=page,pages=(total+29)//30,manager=manager(current_user),sees_all=sees_all(current_user))


@activities_bp.get('/api/assignees')
@login_required
def assignees():
    if not manager(current_user):
        try: parent_id=int(request.args.get('parent_id',''))
        except ValueError: abort(403)
        parent=visible_query(current_user).filter_by(id=parent_id).first()
        if not parent or parent.status not in ACTIVE: abort(403)
    roles = Role.query.filter(Role.weight >= resolve_minimum_weight("staff")).order_by(Role.weight, Role.name).all()
    query = operational_users()
    if request.args.get('role_id'):
        try: role_id = int(request.args['role_id'])
        except ValueError: return error('Ruolo non valido.')
        if role_id not in {role.id for role in roles}: return error('Ruolo non valido.')
        query = query.filter(UserRole.role_id == role_id)
    search = (request.args.get('q') or '').strip()[:120]
    if search: query = query.filter((User.name + ' ' + User.surname).ilike('%' + search + '%'))
    total = query.count()
    users = query.order_by(User.name, User.surname, User.id).limit(100).all()
    return jsonify(ok=True, roles=[dict(id=role.id, name=role.name, weight=role.weight) for role in roles],
                   users=[dict(id=user.id, name=actor_name(user)) for user in users], total=total)


@activities_bp.post('/api')
@login_required
def manual_create():
    parent=None
    try:
        if request.mimetype == 'multipart/form-data':
            if request.headers.get('X-Requested-With') != 'XMLHttpRequest': return error('Usa l’area Attività.',403)
            raw = json.loads(request.form.get('data',''))
        else: raw = request.get_json(silent=True)
        payload = manual_payload(raw)
        parent_id=raw.get('parent_id')
        if parent_id is not None:
            if type(parent_id) is not int: raise ValueError('Attività principale non valida.')
            lock_family(parent_id)
            parent=visible_query(current_user,include_results=manager(current_user)).filter_by(id=parent_id).populate_existing().with_for_update().first()
            if not parent or (not visible_query(current_user).filter_by(id=parent_id).first() and not can_edit(parent,current_user)): abort(404)
            if parent.status not in ACTIVE: raise ValueError('Riapri l’attività principale prima di aggiungere sottoattività.')
            if parent.owner_id and parent.owner_id!=current_user.id and not manager(current_user): abort(403)
            depth=0;ancestor=parent
            while ancestor:
                depth+=1
                ancestor=db.session.get(OperationalActivity,ancestor.parent_id) if ancestor.parent_id else None
            if depth>=8: raise ValueError('Massimo otto livelli di sottoattività.')
            payload['parent_id']=parent_id
        else: office()
        files = prepare_files(request.files.getlist('files'))
        shared=raw.get('share_attachment_ids',[]);photos=raw.get('share_photo_ids',[])
        if any(not isinstance(values,list) or len(values)>10 or any(type(v) is not int for v in values) or len(set(values))!=len(values) for values in [shared,photos]):
            raise ValueError('Allegati condivisi non validi.')
        if (shared or photos) and not parent: raise ValueError('La condivisione richiede un’attività principale.')
        if parent:
            available={f.id:f for f in parent.attachments};available_photos={f.id:f for f in parent.photos}
            if not set(shared)<=available.keys() or not set(photos)<=available_photos.keys(): raise ValueError('Allegato non appartenente all’attività principale.')
            files.extend(dict(filename=available[i].filename,mimetype=available[i].mimetype,size=available[i].size,content=available[i].content) for i in shared)
            for i in photos:
                content=photo_path(available_photos[i].storage_name).read_bytes()
                files.append(dict(filename=f'foto-lotto-{i}.jpg',mimetype='image/jpeg',size=len(content),content=content))
        payload['files_digest'] = files_digest(files)
    except (ValueError, TypeError) as exc: return error(str(exc))
    row = OperationalActivity.query.filter_by(client_key=payload['client_key']).first()
    replayed = row is not None
    if row and not manual_matches(row, payload): return error('La richiesta è già stata usata con dati diversi.', 409)
    if not row:
        if parent and (type(raw.get('parent_revision')) is not int or raw['parent_revision']!=parent.revision): return error('Attività principale cambiata. Aggiorna la scheda.',409)
        try:
            row = create_manual(payload, current_user)
            attach_files(row, files, 'instructions')
            if parent:
                parent.revision+=1;add_event(parent,current_user,'child_created',payload['title'])
                add_event(row,current_user,'linked',f'Sottoattività di #{parent.id}; allegati condivisi: {len(shared)+len(photos)}')
        except ValueError as exc:
            db.session.rollback();return error(str(exc))
        try: db.session.commit()
        except IntegrityError:
            db.session.rollback()
            row = OperationalActivity.query.filter_by(client_key=payload['client_key']).first()
            if not row or not manual_matches(row, payload): return error('Richiesta in conflitto. Riprova.', 409)
            replayed = True
    logger.info('Activity created id=%s actor=%s replayed=%s files=%s',row.id,current_user.id,replayed,len(files))
    return jsonify(ok=True, activity=activity_data(row, current_user, True), replayed=replayed), 200 if replayed else 201


@activities_bp.get('/api/summary')
@login_required
def summary():
    query=activity_query(current_user).filter(OperationalActivity.status.in_(ACTIVE))
    matched={i for i, in query.with_entities(OperationalActivity.id).all()}
    parents=dict(visible_query(current_user,include_results=True).with_entities(OperationalActivity.id,OperationalActivity.parent_id).all())
    def root_id(i):
        visited=set()
        while parents.get(i) in parents and i not in visited:
            visited.add(i);i=parents[i]
        return i
    roots=set(sorted({root_id(i) for i in matched})[:5])
    ids=[i for i in parents if root_id(i) in roots]
    rows=activity_query(current_user).filter(OperationalActivity.id.in_(ids)).order_by(OperationalActivity.created_at,OperationalActivity.id).all()
    return jsonify(ok=True,count=len(matched),rows=[activity_data(row,current_user) for row in rows],manager=manager(current_user),sees_all=sees_all(current_user),results=notices_data(current_user,5))


@activities_bp.get('/api/badge')
@login_required
def badge():
    from tools.activities import badge_count
    return jsonify(ok=True,count=badge_count(current_user))


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
    action_name=payload.get('action')
    try:
        transition(row,current_user,action_name,payload.get('note',''))
        if row.kind=='lots' and action_name=='complete' and row.arrival_id:
            arrival=SupplierArrival.query.filter_by(id=row.arrival_id).first()
            card=SupplierBoardCard.query.filter_by(id=arrival.card_id).with_for_update().first() if arrival and arrival.card_id else None
            if card:
                columns=SupplierBoardColumn.query.all()
                by_name={''.join((column.name or '').casefold().split()):column for column in columns}
                column_by_id={column.id:column for column in columns}
                current_name=''.join((column_by_id[card.column_id].name or '').casefold().split()) if card.column_id in column_by_id else ''
                waiting_names={'inattesadeilotti','inattesalotti'}
                if current_name in waiting_names:
                    destination=by_name.get('dacaricare')
                    if not destination:
                        db.session.rollback()
                        return error('Impossibile spostare la scheda: manca la colonna «Da Caricare».',409)
                    card.column_id=destination.id
                    card.order_revision+=1
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
    try: activity_specs=supplier_arrival_activity_specs(payload)
    except ValueError as exc: return error(str(exc))
    def replay(existing):
        if existing.card_id!=card_id or existing.note!=note.strip() or existing.partial!=partial or existing.received_on!=received:
            return error('Il riferimento dell’arrivo è già usato per dati diversi.',409)
        if activity_specs is not None:
            existing_rows={row.kind:row for row in OperationalActivity.query.filter_by(arrival_id=existing.id).all()}
            if set(existing_rows)!= {spec['kind'] for spec in activity_specs}:
                return error('Il riferimento dell’arrivo è già usato per attività diverse.',409)
            for spec in activity_specs:
                row=existing_rows[spec['kind']];recipients=spec['result_recipients']
                if (sorted(target.role_id for target in row.targets)!=spec['role_ids']
                    or sorted(target.user_id for target in row.user_targets)!=spec['user_ids']
                    or row.target_min_weight!=spec['target_min_weight']
                    or sorted(target.role_id for target in row.result_roles)!=recipients['role_ids']
                    or sorted(target.user_id for target in row.result_users)!=recipients['user_ids']
                    or row.result_min_weight!=recipients['target_min_weight']):
                    return error('Il riferimento dell’arrivo è già usato per destinatari diversi.',409)
        return jsonify(ok=True,arrival_id=existing.id,replayed=True)
    # Serialize arrivals for the same card, then recheck the idempotency key.
    card=SupplierBoardCard.query.filter_by(id=card_id).with_for_update().first()
    existing=SupplierArrival.query.filter_by(event_key=key).first()
    if existing: return replay(existing)
    if not card or card.is_archived or card.is_draft: return error('Scheda non disponibile per un nuovo arrivo.',404)
    if type(payload.get('revision')) is not int or payload['revision']!=card.order_revision: return error('La scheda è cambiata. Riapri il nuovo arrivo.',409)
    body=dict(payload,event_key=key,note=note.strip(),partial=partial,_activity_specs=activity_specs)
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
    if not item or not visible_query(current_user,include_results=True).filter_by(id=item.activity_id).first(): abort(404)
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


@activities_bp.get('/api/results')
@login_required
def results():
    return jsonify(ok=True,**notices_data(current_user))


@activities_bp.post('/api/results/<int:notice_id>/read')
@login_required
def read_result(notice_id):
    row=notices_query(current_user).filter(ActivityResultNotice.id==notice_id).first_or_404()
    row.read_at=datetime.utcnow();db.session.commit()
    return jsonify(ok=True)


@activities_bp.post('/api/<int:activity_id>/attachments')
@login_required
def upload_attachments(activity_id):
    if request.headers.get('X-Requested-With')!='XMLHttpRequest': return error('Usa l’area Attività.',403)
    try: revision=int(request.form.get('revision',''))
    except ValueError: return error('Revisione non valida.')
    row,conflict=locked_activity(activity_id,revision)
    if conflict: return conflict
    if row.status not in ACTIVE: return error('L’attività è chiusa.')
    if row.owner_id and row.owner_id!=current_user.id and not manager(current_user): return error('Attività in carico a un’altra persona.',403)
    try:
        files=prepare_files(request.files.getlist('files'))
        if not files: raise ValueError('Scegli almeno un file o una foto.')
        attach_files(row,files,'result')
        row.revision+=1;add_event(row,current_user,'files_added',', '.join(item['filename'] for item in files))
        db.session.commit()
    except ValueError as exc:
        db.session.rollback();return error(str(exc))
    logger.info('Activity files added id=%s actor=%s count=%s',row.id,current_user.id,len(files))
    return jsonify(ok=True,activity=activity_data(row,current_user,True)),201


@activities_bp.get('/api/attachments/<int:attachment_id>')
@login_required
def download_attachment(attachment_id):
    item=db.session.get(ActivityAttachment,attachment_id)
    if not item or not visible_query(current_user,include_results=True).filter_by(id=item.activity_id).first(): abort(404)
    response=send_file(BytesIO(item.content),mimetype=item.mimetype,download_name=item.filename,as_attachment=True,max_age=0)
    response.headers['Cache-Control']='private, no-store';response.headers['X-Content-Type-Options']='nosniff'
    return response


@activities_bp.delete('/api/attachments/<int:attachment_id>')
@login_required
def delete_attachment(attachment_id):
    item=db.session.get(ActivityAttachment,attachment_id)
    if not item: abort(404)
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return error('Dati non validi.')
    row,conflict=locked_activity(item.activity_id,payload.get('revision'))
    if conflict: return conflict
    if row.status not in ACTIVE or item.cycle!=row.cycle or item.purpose!='result': return error('Gli allegati delle istruzioni e dello storico sono conservati.')
    if row.owner_id and row.owner_id!=current_user.id and not manager(current_user): return error('Attività in carico a un’altra persona.',403)
    add_event(row,current_user,'file_removed',item.filename);db.session.delete(item);row.revision+=1;db.session.commit()
    db.session.expire(row,['attachments'])
    logger.info('Activity file removed id=%s attachment=%s actor=%s',row.id,attachment_id,current_user.id)
    return jsonify(ok=True,activity=activity_data(row,current_user,True))


@activities_bp.put('/api/<int:activity_id>')
@login_required
def edit_activity(activity_id):
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return error('Dati non validi.')
    lock_family(activity_id)
    row=visible_query(current_user,include_results=True).filter_by(id=activity_id).populate_existing().with_for_update().first_or_404()
    if not can_edit(row,current_user): abort(403)
    if type(payload.get('revision')) is not int or payload['revision']!=row.revision: return error('Attività cambiata. Aggiorna il dettaglio.',409)
    try:
        # Use the creation validator and the same active recipient validation.
        normalized=manual_payload({**payload,'client_key':'edit-validation-key'})
        from tools.activities import validate_manual_targets
        validate_manual_targets(normalized)
        before=dict(title=row.title,description=row.description,roles=sorted(t.role_id for t in row.targets),users=sorted(t.user_id for t in row.user_targets),weight=row.target_min_weight,
            result_roles=sorted(t.role_id for t in row.result_roles),result_users=sorted(t.user_id for t in row.result_users),result_weight=row.result_min_weight)
        after=dict(title=normalized['title'],description=normalized['description'],roles=normalized['role_ids'],users=normalized['user_ids'],weight=normalized['target_min_weight'],
            result_roles=normalized['result_recipients']['role_ids'],result_users=normalized['result_recipients']['user_ids'],result_weight=normalized['result_recipients']['target_min_weight'])
        if before==after: return jsonify(ok=True,activity=activity_data(row,current_user,True))
        from tools.activities import notification_recipients
        previous=notification_recipients(row)
        row.title=after['title'];row.description=after['description']
        from models import ActivityTargetRole, ActivityTargetUser, ActivityResultRole, ActivityResultUser
        for relation,model,key,values in [('targets',ActivityTargetRole,'role_id',after['roles']),('user_targets',ActivityTargetUser,'user_id',after['users']),('result_roles',ActivityResultRole,'role_id',after['result_roles']),('result_users',ActivityResultUser,'user_id',after['result_users'])]:
            existing={getattr(item,key):item for item in getattr(row,relation)}
            getattr(row,relation)[:]=[existing[v] if v in existing else model(**{key:v}) for v in values]
        row.target_min_weight=after['weight'];row.result_min_weight=after['result_weight'];row.revision+=1
        changes=[name for name in before if before[name]!=after[name]]
        labels=dict(title='Titolo',description='Descrizione',roles='Ruoli incaricati',users='Utenti incaricati',weight='Peso minimo incaricati',result_roles='Ruoli destinatari',result_users='Utenti destinatari',result_weight='Peso minimo destinatari')
        role_ids=set(before['roles']+before['result_roles']+after['roles']+after['result_roles'])
        user_ids=set(before['users']+before['result_users']+after['users']+after['result_users'])
        role_names={r.id:r.name for r in Role.query.filter(Role.id.in_(role_ids)).all()}
        user_names={u.id:actor_name(u) for u in User.query.filter(User.id.in_(user_ids)).all()}
        def describe(data):
            parts=[]
            for field in changes:
                value=data[field]
                if field in ('roles','result_roles'): value=', '.join(role_names.get(i,str(i)) for i in value) or 'Nessuno'
                if field in ('users','result_users'): value=', '.join(user_names.get(i,str(i)) for i in value) or 'Nessuno'
                parts.append(labels[field]+': '+str(value if value is not None else 'Nessuno'))
            return '\n'.join(parts)
        add_event(row,current_user,'updated','Modificati: '+', '.join(labels[k] for k in changes)+'\nPrima:\n'+describe(before)+'\nDopo:\n'+describe(after))
        from tools.activities import create_result_notices
        create_result_notices(row,previous)
        db.session.commit()
        logger.info('Activity updated id=%s actor=%s fields=%s',row.id,current_user.id,changes)
        return jsonify(ok=True,activity=activity_data(row,current_user,True))
    except ValueError as exc:
        db.session.rollback();return error(str(exc))

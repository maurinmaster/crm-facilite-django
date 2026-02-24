import json
import uuid

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .auth import get_session
from .models import Client, ClientContact, ClientCredentialSimple, ClientLink


def _resolve_user_ctx(request):
    if getattr(request, 'user_ctx', None):
        return request.user_ctx

    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    token = None
    if auth_header.lower().startswith('bearer '):
        token = auth_header[7:].strip()
    if not token:
        token = request.COOKIES.get('crm_session')

    ctx = get_session(token)
    if ctx:
        request.user_ctx = ctx
    return ctx


def _auth_required(request):
    ctx = _resolve_user_ctx(request)
    if not ctx:
        return JsonResponse({'detail': 'Não autenticado'}, status=401)
    return None


def _admin_required(request):
    guard = _auth_required(request)
    if guard:
        return guard
    user = request.user_ctx['user']
    if not user.is_admin:
        return JsonResponse({'detail': 'Acesso negado (admin)'}, status=403)
    return None


def _as_int(value, default, minimum=0, maximum=200):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, n))


def _json_body(request):
    try:
        raw = request.body.decode('utf-8') if request.body else '{}'
        data = json.loads(raw or '{}')
        return data if isinstance(data, dict) else {}
    except Exception:
        return None


def _new_text_id():
    return str(uuid.uuid4())


@require_GET
def api_health(request):
    return JsonResponse({'ok': True, 'service': 'facilite-crm-django'})


@require_GET
def api_me(request):
    guard = _auth_required(request)
    if guard:
        return guard

    user = request.user_ctx['user']
    return JsonResponse({
        'id': str(user.id),
        'email': user.email,
        'name': user.name,
        'is_admin': user.is_admin,
    })


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_clients(request):
    guard = _auth_required(request)
    if guard:
        return guard

    if request.method == 'GET':
        q = (request.GET.get('q') or '').strip()
        limit = _as_int(request.GET.get('limit'), default=50, minimum=1, maximum=200)
        offset = _as_int(request.GET.get('offset'), default=0, minimum=0, maximum=100000)

        qs = Client.objects.all().order_by('name', 'id')
        if q:
            qs = qs.filter(name__icontains=q)

        total = qs.count()
        items = list(qs[offset:offset + limit].values(
            'id', 'org_id', 'name', 'cnpj', 'status', 'type', 'notes', 'updated_at', 'created_at'
        ))

        return JsonResponse({'count': total, 'limit': limit, 'offset': offset, 'results': items})

    data = _json_body(request)
    if data is None:
        return JsonResponse({'detail': 'JSON inválido'}, status=400)

    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'detail': 'Campo "name" é obrigatório'}, status=400)

    now = timezone.now()
    client = Client.objects.create(
        id=(data.get('id') or _new_text_id()),
        org_id=data.get('org_id'),
        name=name,
        cnpj=data.get('cnpj'),
        status=data.get('status'),
        type=data.get('type'),
        notes=data.get('notes'),
        updated_at=now,
        created_at=now,
    )

    return JsonResponse({'id': client.id, 'detail': 'Cliente criado com sucesso'}, status=201)


@csrf_exempt
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def api_client_detail(request, client_id):
    guard = _auth_required(request)
    if guard:
        return guard

    client_obj = Client.objects.filter(id=client_id).first()
    if not client_obj:
        return JsonResponse({'detail': 'Cliente não encontrado'}, status=404)

    if request.method == 'GET':
        client = Client.objects.filter(id=client_id).values(
            'id', 'org_id', 'name', 'cnpj', 'status', 'type', 'notes', 'updated_at', 'created_at'
        ).first()
        contacts = list(ClientContact.objects.filter(client_id=client_id).values(
            'id', 'client_id', 'name', 'role', 'department', 'phone', 'email', 'instagram', 'notes', 'created_at'
        ))
        credentials = list(ClientCredentialSimple.objects.filter(client_id=client_id).values(
            'id', 'client_id', 'site', 'usuario', 'senha', 'token', 'obs', 'created_at'
        ))
        links = list(ClientLink.objects.filter(client_id=client_id).values(
            'id', 'client_id', 'name', 'url', 'created_at'
        ))

        return JsonResponse({'client': client, 'contacts': contacts, 'credentials': credentials, 'links': links})

    if request.method in ('PUT', 'PATCH'):
        data = _json_body(request)
        if data is None:
            return JsonResponse({'detail': 'JSON inválido'}, status=400)

        fields = ['org_id', 'name', 'cnpj', 'status', 'type', 'notes']
        changed = []
        for f in fields:
            if f in data:
                setattr(client_obj, f, data.get(f))
                changed.append(f)

        if 'name' in changed and not (client_obj.name or '').strip():
            return JsonResponse({'detail': 'Campo "name" não pode ficar vazio'}, status=400)

        client_obj.updated_at = timezone.now()
        changed.append('updated_at')
        client_obj.save(update_fields=changed)
        return JsonResponse({'detail': 'Cliente atualizado com sucesso'})

    admin_guard = _admin_required(request)
    if admin_guard:
        return admin_guard

    ClientContact.objects.filter(client_id=client_id).delete()
    ClientCredentialSimple.objects.filter(client_id=client_id).delete()
    ClientLink.objects.filter(client_id=client_id).delete()
    client_obj.delete()
    return JsonResponse({'detail': 'Cliente removido com sucesso'})


# -------- Contacts --------
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_client_contacts(request, client_id):
    guard = _auth_required(request)
    if guard:
        return guard

    if not Client.objects.filter(id=client_id).exists():
        return JsonResponse({'detail': 'Cliente não encontrado'}, status=404)

    if request.method == 'GET':
        items = list(ClientContact.objects.filter(client_id=client_id).values(
            'id', 'client_id', 'name', 'role', 'department', 'phone', 'email', 'instagram', 'notes', 'created_at'
        ))
        return JsonResponse({'count': len(items), 'results': items})

    data = _json_body(request)
    if data is None:
        return JsonResponse({'detail': 'JSON inválido'}, status=400)

    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'detail': 'Campo "name" é obrigatório'}, status=400)

    contact = ClientContact.objects.create(
        id=(data.get('id') or _new_text_id()),
        client_id=client_id,
        name=name,
        role=data.get('role'),
        department=data.get('department'),
        phone=data.get('phone'),
        email=data.get('email'),
        instagram=data.get('instagram'),
        notes=data.get('notes'),
        created_at=timezone.now(),
    )
    return JsonResponse({'id': contact.id, 'detail': 'Contato criado com sucesso'}, status=201)


@csrf_exempt
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def api_contact_detail(request, contact_id):
    guard = _auth_required(request)
    if guard:
        return guard

    obj = ClientContact.objects.filter(id=contact_id).first()
    if not obj:
        return JsonResponse({'detail': 'Contato não encontrado'}, status=404)

    if request.method == 'GET':
        item = ClientContact.objects.filter(id=contact_id).values(
            'id', 'client_id', 'name', 'role', 'department', 'phone', 'email', 'instagram', 'notes', 'created_at'
        ).first()
        return JsonResponse(item)

    if request.method in ('PUT', 'PATCH'):
        data = _json_body(request)
        if data is None:
            return JsonResponse({'detail': 'JSON inválido'}, status=400)

        fields = ['name', 'role', 'department', 'phone', 'email', 'instagram', 'notes']
        changed = []
        for f in fields:
            if f in data:
                setattr(obj, f, data.get(f))
                changed.append(f)

        if 'name' in changed and not (obj.name or '').strip():
            return JsonResponse({'detail': 'Campo "name" não pode ficar vazio'}, status=400)

        if not changed:
            return JsonResponse({'detail': 'Nada para atualizar'})

        obj.save(update_fields=changed)
        return JsonResponse({'detail': 'Contato atualizado com sucesso'})

    admin_guard = _admin_required(request)
    if admin_guard:
        return admin_guard

    obj.delete()
    return JsonResponse({'detail': 'Contato removido com sucesso'})


# -------- Credentials --------
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_client_credentials(request, client_id):
    guard = _auth_required(request)
    if guard:
        return guard

    if not Client.objects.filter(id=client_id).exists():
        return JsonResponse({'detail': 'Cliente não encontrado'}, status=404)

    if request.method == 'GET':
        items = list(ClientCredentialSimple.objects.filter(client_id=client_id).values(
            'id', 'client_id', 'site', 'usuario', 'senha', 'token', 'obs', 'created_at'
        ))
        return JsonResponse({'count': len(items), 'results': items})

    data = _json_body(request)
    if data is None:
        return JsonResponse({'detail': 'JSON inválido'}, status=400)

    site = (data.get('site') or '').strip()
    if not site:
        return JsonResponse({'detail': 'Campo "site" é obrigatório'}, status=400)

    obj = ClientCredentialSimple.objects.create(
        id=(data.get('id') or _new_text_id()),
        client_id=client_id,
        site=site,
        usuario=data.get('usuario'),
        senha=data.get('senha'),
        token=data.get('token'),
        obs=data.get('obs'),
        created_at=timezone.now(),
    )
    return JsonResponse({'id': obj.id, 'detail': 'Credencial criada com sucesso'}, status=201)


@csrf_exempt
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def api_credential_detail(request, credential_id):
    guard = _auth_required(request)
    if guard:
        return guard

    obj = ClientCredentialSimple.objects.filter(id=credential_id).first()
    if not obj:
        return JsonResponse({'detail': 'Credencial não encontrada'}, status=404)

    if request.method == 'GET':
        item = ClientCredentialSimple.objects.filter(id=credential_id).values(
            'id', 'client_id', 'site', 'usuario', 'senha', 'token', 'obs', 'created_at'
        ).first()
        return JsonResponse(item)

    if request.method in ('PUT', 'PATCH'):
        data = _json_body(request)
        if data is None:
            return JsonResponse({'detail': 'JSON inválido'}, status=400)

        fields = ['site', 'usuario', 'senha', 'token', 'obs']
        changed = []
        for f in fields:
            if f in data:
                setattr(obj, f, data.get(f))
                changed.append(f)

        if 'site' in changed and not (obj.site or '').strip():
            return JsonResponse({'detail': 'Campo "site" não pode ficar vazio'}, status=400)

        if not changed:
            return JsonResponse({'detail': 'Nada para atualizar'})

        obj.save(update_fields=changed)
        return JsonResponse({'detail': 'Credencial atualizada com sucesso'})

    admin_guard = _admin_required(request)
    if admin_guard:
        return admin_guard

    obj.delete()
    return JsonResponse({'detail': 'Credencial removida com sucesso'})


# -------- Links --------
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_client_links(request, client_id):
    guard = _auth_required(request)
    if guard:
        return guard

    if not Client.objects.filter(id=client_id).exists():
        return JsonResponse({'detail': 'Cliente não encontrado'}, status=404)

    if request.method == 'GET':
        items = list(ClientLink.objects.filter(client_id=client_id).values(
            'id', 'client_id', 'name', 'url', 'created_at'
        ))
        return JsonResponse({'count': len(items), 'results': items})

    data = _json_body(request)
    if data is None:
        return JsonResponse({'detail': 'JSON inválido'}, status=400)

    name = (data.get('name') or '').strip()
    url = (data.get('url') or '').strip()
    if not name:
        return JsonResponse({'detail': 'Campo "name" é obrigatório'}, status=400)
    if not url:
        return JsonResponse({'detail': 'Campo "url" é obrigatório'}, status=400)

    obj = ClientLink.objects.create(
        id=(data.get('id') or _new_text_id()),
        client_id=client_id,
        name=name,
        url=url,
        created_at=timezone.now(),
    )
    return JsonResponse({'id': obj.id, 'detail': 'Link criado com sucesso'}, status=201)


@csrf_exempt
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def api_link_detail(request, link_id):
    guard = _auth_required(request)
    if guard:
        return guard

    obj = ClientLink.objects.filter(id=link_id).first()
    if not obj:
        return JsonResponse({'detail': 'Link não encontrado'}, status=404)

    if request.method == 'GET':
        item = ClientLink.objects.filter(id=link_id).values(
            'id', 'client_id', 'name', 'url', 'created_at'
        ).first()
        return JsonResponse(item)

    if request.method in ('PUT', 'PATCH'):
        data = _json_body(request)
        if data is None:
            return JsonResponse({'detail': 'JSON inválido'}, status=400)

        fields = ['name', 'url']
        changed = []
        for f in fields:
            if f in data:
                setattr(obj, f, data.get(f))
                changed.append(f)

        if 'name' in changed and not (obj.name or '').strip():
            return JsonResponse({'detail': 'Campo "name" não pode ficar vazio'}, status=400)
        if 'url' in changed and not (obj.url or '').strip():
            return JsonResponse({'detail': 'Campo "url" não pode ficar vazio'}, status=400)

        if not changed:
            return JsonResponse({'detail': 'Nada para atualizar'})

        obj.save(update_fields=changed)
        return JsonResponse({'detail': 'Link atualizado com sucesso'})

    admin_guard = _admin_required(request)
    if admin_guard:
        return admin_guard

    obj.delete()
    return JsonResponse({'detail': 'Link removido com sucesso'})

# API_TESTS.md

Guia rápido para testar a API do `facilite-crm-django`.

## 1) Variáveis

```bash
export BASE_URL="http://127.0.0.1:8000"
export TOKEN="SEU_TOKEN_DA_TABELA_SESSIONS"
```

> Autenticação: `Authorization: Bearer $TOKEN`

---

## 2) Health / usuário

```bash
curl "$BASE_URL/api/health/"

curl "$BASE_URL/api/me/" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 3) Clientes

### Listar
```bash
curl "$BASE_URL/api/clients/?q=&limit=20&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

### Criar
```bash
curl -X POST "$BASE_URL/api/clients/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Cliente API Teste",
    "cnpj": "00.000.000/0001-00",
    "status": "ativo",
    "type": "agencia",
    "notes": "Criado via API"
  }'
```

### Detalhar
```bash
export CLIENT_ID="ID_DO_CLIENTE"
curl "$BASE_URL/api/clients/$CLIENT_ID/" \
  -H "Authorization: Bearer $TOKEN"
```

### Atualizar
```bash
curl -X PATCH "$BASE_URL/api/clients/$CLIENT_ID/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes":"Atualizado via PATCH"}'
```

### Deletar (admin)
```bash
curl -X DELETE "$BASE_URL/api/clients/$CLIENT_ID/" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 4) Contatos

### Listar
```bash
curl "$BASE_URL/api/clients/$CLIENT_ID/contacts/" \
  -H "Authorization: Bearer $TOKEN"
```

### Criar
```bash
curl -X POST "$BASE_URL/api/clients/$CLIENT_ID/contacts/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"João Contato",
    "role":"Gestor",
    "department":"Comercial",
    "phone":"+55 11 99999-9999",
    "email":"joao@cliente.com"
  }'
```

### Atualizar
```bash
export CONTACT_ID="ID_DO_CONTATO"
curl -X PATCH "$BASE_URL/api/contacts/$CONTACT_ID/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+55 11 98888-8888"}'
```

### Deletar (admin)
```bash
curl -X DELETE "$BASE_URL/api/contacts/$CONTACT_ID/" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 5) Credenciais

### Listar
```bash
curl "$BASE_URL/api/clients/$CLIENT_ID/credentials/" \
  -H "Authorization: Bearer $TOKEN"
```

### Criar
```bash
curl -X POST "$BASE_URL/api/clients/$CLIENT_ID/credentials/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site":"https://painel.exemplo.com",
    "usuario":"usuario_teste",
    "senha":"senha_teste",
    "token":"token_teste",
    "obs":"Credencial criada via API"
  }'
```

### Atualizar
```bash
export CREDENTIAL_ID="ID_DA_CREDENCIAL"
curl -X PATCH "$BASE_URL/api/credentials/$CREDENTIAL_ID/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"obs":"Atualizada via PATCH"}'
```

### Deletar (admin)
```bash
curl -X DELETE "$BASE_URL/api/credentials/$CREDENTIAL_ID/" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 6) Links

### Listar
```bash
curl "$BASE_URL/api/clients/$CLIENT_ID/links/" \
  -H "Authorization: Bearer $TOKEN"
```

### Criar
```bash
curl -X POST "$BASE_URL/api/clients/$CLIENT_ID/links/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Drive do Cliente",
    "url":"https://drive.google.com/..."
  }'
```

### Atualizar
```bash
export LINK_ID="ID_DO_LINK"
curl -X PATCH "$BASE_URL/api/links/$LINK_ID/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Drive Oficial"}'
```

### Deletar (admin)
```bash
curl -X DELETE "$BASE_URL/api/links/$LINK_ID/" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 7) Subir servidor local (desenvolvimento)

```bash
cd /root/apps/facilite-crm-django
pip install -r requirements.txt
python manage.py runserver 0.0.0.0:8000
```

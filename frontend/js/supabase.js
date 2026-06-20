const SUPABASE_URL = 'https://oaqmnaekrpukwmrxjtud.supabase.co'
const SUPABASE_ANON_KEY = 'sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR'

let _supabase = null
try {
  if (typeof supabase !== 'undefined' && supabase.createClient) {
    _supabase = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  }
} catch (e) {
  console.warn('Supabase client nao disponivel:', e)
}

function _check() { if (!_supabase) throw new Error('Supabase SDK nao carregado') }

// ─── Auth ─────────────────────────────────────────────
async function signUp(email, password) {
  _check()
  const { data, error } = await _supabase.auth.signUp({ email, password })
  if (error) throw error
  return data
}

async function signIn(email, password) {
  _check()
  const { data, error } = await _supabase.auth.signInWithPassword({ email, password })
  if (error) throw error
  return data
}

async function signOut() {
  _check()
  const { error } = await _supabase.auth.signOut()
  if (error) throw error
}

function getSession() {
  _check()
  return _supabase.auth.getSession()
}

// ─── Setups CRUD ─────────────────────────────────────
async function salvarSetup(nome, filtros) {
  _check()
  const user = (await _supabase.auth.getSession())?.data?.session?.user
  if (!user) throw new Error('Usuário não autenticado')
  const { data, error } = await _supabase
    .from('setups')
    .insert({ user_id: user.id, nome, filtros })
    .select()
    .single()
  if (error) throw error
  return data
}

async function listarSetups() {
  _check()
  const { data, error } = await _supabase
    .from('setups')
    .select('*')
    .order('created_at', { ascending: false })
  if (error) throw error
  return data || []
}

async function atualizarSetup(id, updates) {
  _check()
  const { data, error } = await _supabase
    .from('setups')
    .update({ ...updates, updated_at: new Date().toISOString() })
    .eq('id', id)
    .select()
    .single()
  if (error) throw error
  return data
}

async function deletarSetup(id) {
  _check()
  const { error } = await _supabase
    .from('setups')
    .delete()
    .eq('id', id)
  if (error) throw error
}

// ─── User Ativos CRUD ────────────────────────────
async function listarAtivos() {
  const uid=_userId()
  if(!uid)throw new Error('Usuário não autenticado')
  const r=await _api('user_ativos?select=*&user_id=eq.'+uid+'&order=ticker.asc')
  if(!r.ok)throw new Error(await r.text())
  return await r.json()
}

async function adicionarAtivo(ticker, quantidade) {
  const uid=_userId()
  if(!uid)throw new Error('Usuário não autenticado')
  const r=await _api('user_ativos',{method:'POST',body:JSON.stringify({user_id:uid,ticker,quantidade})})
  if(!r.ok)throw new Error(await r.text())
  return await r.json()
}

async function atualizarAtivo(id, quantidade) {
  const r=await _api('user_ativos?id=eq.'+id,{method:'PATCH',body:JSON.stringify({quantidade,updated_at:new Date().toISOString()})})
  if(!r.ok)throw new Error(await r.text())
}

async function deletarAtivo(id) {
  const r=await _api('user_ativos?id=eq.'+id,{method:'DELETE'})
  if(!r.ok)throw new Error(await r.text())
}

function _token(){
  for(let i=0;i<localStorage.length;i++){
    const k=localStorage.key(i)
    if(k&&k.startsWith('sb-')&&k.endsWith('-auth-token')){
      try{
        const d=JSON.parse(localStorage.getItem(k))
        if(d&&d.access_token&&(!d.expires_at||d.expires_at*1000>Date.now()))return d
      }catch(e){}
    }
  }
  return null
}

function _userId(){
  try{
    const t=_token()
    if(!t)return null
    // Try all known locations for user id
    if(t.user?.id)return t.user.id
    if(t.identities?.length&&t.identities[0].user_id)return t.identities[0].user_id
    if(t.sub)return t.sub
    // Decode JWT sub (base64url -> base64)
    const raw=t.access_token
    const p=raw.split('.')[1]
    if(!p)return null
    let b64=p.replace(/-/g,'+').replace(/_/g,'/')
    while(b64.length%4)b64+='='
    const d=JSON.parse(atob(b64))
    return d.sub||null
  }catch(e){}
  return null
}

function _api(path,opts){
  const t=_token()
  if(!t)return Promise.reject(new Error('Não autenticado'))
  return fetch(SUPABASE_URL+'/rest/v1/'+path,{...opts,headers:{'Content-Type':'application/json',apikey:SUPABASE_ANON_KEY,Authorization:'Bearer '+t.access_token,...opts?.headers}})
}

// ─── User Profile CRUD ──────────────────────────
async function getProfile() {
  const uid=_userId()
  if(!uid)throw new Error('Usuário não autenticado')
  const r=await _api('user_profiles?user_id=eq.'+uid+'&limit=1')
  if(!r.ok)throw new Error(await r.text())
  const d=await r.json()
  return d&&d.length?d[0]:null
}

async function upsertProfile(profile) {
  const uid=_userId()
  if(!uid)throw new Error('Usuário não autenticado')
  // Try update first
  const up=await _api('user_profiles?user_id=eq.'+uid,{method:'PATCH',body:JSON.stringify({...profile,updated_at:new Date().toISOString()})})
  if(up.ok)return
  // If no row to update, insert
  const r=await _api('user_profiles',{method:'POST',body:JSON.stringify({user_id:uid,...profile,updated_at:new Date().toISOString()})})
  if(!r.ok)throw new Error(await r.text())
}

async function resetSenha(email) {
  _check()
  const { error } = await _supabase.auth.resetPasswordForEmail(email, {
    redirectTo: window.location.origin + '/pages/recuperar-senha.html'
  })
  if (error) throw error
}

async function updatePassword(currentPassword, newPassword) {
  _check()
  const user = (await _supabase.auth.getSession())?.data?.session?.user
  if (!user) throw new Error('Usuário não autenticado')
  // Re-authenticate to verify current password
  const { error: signInError } = await _supabase.auth.signInWithPassword({
    email: user.email,
    password: currentPassword
  })
  if (signInError) throw new Error('Senha atual incorreta')
  const { error } = await _supabase.auth.updateUser({ password: newPassword })
  if (error) throw error
}

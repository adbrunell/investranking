const SUPABASE_URL = 'https://oaqmnaekrpukwmrxjtud.supabase.co'
const SUPABASE_ANON_KEY = 'sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR'
const AUTH_KEY = 'ir_auth'

let _supabase = null
try {
  if (typeof supabase !== 'undefined' && supabase.createClient) {
    _supabase = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  }
} catch (e) {
  console.warn('Supabase client nao disponivel:', e)
}

function _check() { if (!_supabase) throw new Error('Supabase SDK nao carregado') }

// ─── Custom Auth Storage (bypass Supabase internal storage) ──
function _salvarAuth(data){
  try{
    if(data?.session){
      localStorage.setItem(AUTH_KEY,JSON.stringify({
        access_token:data.session.access_token,
        refresh_token:data.session.refresh_token,
        user:data.session.user,
        expires_at:data.session.expires_at,
        saved_at:Date.now()
      }))
    }
  }catch(e){}
}

function _limparAuth(){
  try{localStorage.removeItem(AUTH_KEY)}catch(e){}
}

function _getAuth(){
  try{
    const d=localStorage.getItem(AUTH_KEY)
    if(!d)return null
    const p=JSON.parse(d)
    if(!p.access_token)return null
    if(p.expires_at&&p.expires_at*1000<Date.now()){_limparAuth();return null}
    return p
  }catch(e){}
  return null
}

function _userId(){
  try{
    const a=_getAuth()
    if(!a)return null
    if(a.user?.id)return a.user.id
    // Decode JWT
    const p=a.access_token.split('.')[1]
    if(!p)return null
    let b64=p.replace(/-/g,'+').replace(/_/g,'/')
    while(b64.length%4)b64+='='
    return JSON.parse(atob(b64)).sub||null
  }catch(e){}
  return null
}

function _api(path,opts){
  const a=_getAuth()
  if(!a)return Promise.reject(new Error('Não autenticado'))
  return fetch(SUPABASE_URL+'/rest/v1/'+path,{...opts,headers:{'Content-Type':'application/json',apikey:SUPABASE_ANON_KEY,Authorization:'Bearer '+a.access_token,...opts?.headers}})
}

// ─── Auth ─────────────────────────────────────────────
async function signUp(email, password) {
  _check()
  const { data, error } = await _supabase.auth.signUp({ email, password })
  if (error) throw error
  _salvarAuth(data)
  return data
}

async function signIn(email, password) {
  _check()
  const { data, error } = await _supabase.auth.signInWithPassword({ email, password })
  if (error) throw error
  _salvarAuth(data)
  return data
}

async function signOut() {
  _limparAuth()
  try{_check();await _supabase.auth.signOut()}catch(e){}
}

function getSession() {
  const a=_getAuth()
  return Promise.resolve({data:{session:a?{user:a.user,access_token:a.access_token,refresh_token:a.refresh_token}:null}})
}

// ─── Setups CRUD (uses Supabase client, works with parent scope) ──
async function salvarSetup(nome, filtros) {
  _check()
  const user = _getAuth()?.user
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
  const r=await _api('user_ativos?select=*',{method:'POST',headers:{'Prefer':'return=representation'},body:JSON.stringify({user_id:uid,ticker,quantidade})})
  if(!r.ok)throw new Error(await r.text())
  const d=await r.json()
  return Array.isArray(d)?d[0]:d
}

async function atualizarAtivo(id, quantidade) {
  const r=await _api('user_ativos?id=eq.'+id,{method:'PATCH',body:JSON.stringify({quantidade,updated_at:new Date().toISOString()})})
  if(!r.ok)throw new Error(await r.text())
}

async function deletarAtivo(id) {
  const r=await _api('user_ativos?id=eq.'+id,{method:'DELETE'})
  if(!r.ok)throw new Error(await r.text())
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
  // Use POST with on_conflict for true upsert
  const r=await _api('user_profiles?on_conflict=user_id',{method:'POST',headers:{Prefer:'resolution=merge-duplicates'},body:JSON.stringify({user_id:uid,...profile,updated_at:new Date().toISOString()})})
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
  const a=_getAuth()
  if(!a)throw new Error('Usuário não autenticado')
  // Re-authenticate via REST API
  const r=await fetch(SUPABASE_URL+'/rest/v1/rpc/login',{method:'POST',headers:{'Content-Type':'application/json',apikey:SUPABASE_ANON_KEY},body:JSON.stringify({email:a.user.email,password:currentPassword})})
  if(!r.ok)throw new Error('Senha atual incorreta')
  // Update password via Supabase client
  _check()
  const sess=await _supabase.auth.getSession()
  if(!sess?.data?.session)await _supabase.auth.setSession({access_token:a.access_token,refresh_token:a.refresh_token})
  const {error}=await _supabase.auth.updateUser({password:newPassword})
  if(error)throw error
}
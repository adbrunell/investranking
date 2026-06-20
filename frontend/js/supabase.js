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
  _check()
  const user = (await _supabase.auth.getSession())?.data?.session?.user
  if (!user) throw new Error('Usuário não autenticado')
  const { data, error } = await _supabase
    .from('user_ativos')
    .select('*')
    .eq('user_id', user.id)
    .order('ticker', { ascending: true })
  if (error) throw error
  return data || []
}

async function adicionarAtivo(ticker, quantidade) {
  _check()
  const user = (await _supabase.auth.getSession())?.data?.session?.user
  if (!user) throw new Error('Usuário não autenticado')
  const { data, error } = await _supabase
    .from('user_ativos')
    .insert({ user_id: user.id, ticker, quantidade })
    .select()
    .single()
  if (error) throw error
  return data
}

async function atualizarAtivo(id, quantidade) {
  _check()
  const { data, error } = await _supabase
    .from('user_ativos')
    .update({ quantidade, updated_at: new Date().toISOString() })
    .eq('id', id)
    .select()
    .single()
  if (error) throw error
  return data
}

async function deletarAtivo(id) {
  _check()
  const { error } = await _supabase
    .from('user_ativos')
    .delete()
    .eq('id', id)
  if (error) throw error
}

// ─── User Profile CRUD ──────────────────────────
async function getProfile() {
  _check()
  const user = (await _supabase.auth.getSession())?.data?.session?.user
  if (!user) throw new Error('Usuário não autenticado')
  const { data, error } = await _supabase
    .from('user_profiles')
    .select('*')
    .eq('user_id', user.id)
    .maybeSingle()
  if (error) throw error
  return data || null
}

async function upsertProfile(profile) {
  _check()
  const user = (await _supabase.auth.getSession())?.data?.session?.user
  if (!user) throw new Error('Usuário não autenticado')
  const payload = { user_id: user.id, ...profile, updated_at: new Date().toISOString() }
  const { data, error } = await _supabase
    .from('user_profiles')
    .upsert(payload, { onConflict: 'user_id' })
    .select()
    .single()
  if (error) throw error
  return data
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

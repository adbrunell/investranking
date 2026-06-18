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
  const { data, error } = await _supabase
    .from('setups')
    .insert({ nome, filtros })
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

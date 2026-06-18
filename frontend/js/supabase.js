const SUPABASE_URL = 'https://oaqmnaekrpukwmrxjtud.supabase.co'
const SUPABASE_ANON_KEY = 'sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR'
const _supabase = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

// ─── Auth ─────────────────────────────────────────────
async function signUp(email, password) {
  const { data, error } = await _supabase.auth.signUp({ email, password })
  if (error) throw error
  return data
}

async function signIn(email, password) {
  const { data, error } = await _supabase.auth.signInWithPassword({ email, password })
  if (error) throw error
  return data
}

async function signOut() {
  const { error } = await _supabase.auth.signOut()
  if (error) throw error
}

function getSession() {
  return _supabase.auth.getSession()
}

function onAuthChange(callback) {
  return _supabase.auth.onAuthStateChange(callback)
}

// ─── Session token for PostgREST ──────────────────────
async function authHeaders() {
  const { data } = await getSession()
  const token = data?.session?.access_token
  return token
    ? { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${token}` }
    : { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${SUPABASE_ANON_KEY}` }
}

// ─── Setups CRUD ─────────────────────────────────────
async function salvarSetup(nome, filtros) {
  const h = await authHeaders()
  const { data, error } = await _supabase
    .from('setups')
    .insert({ nome, filtros })
    .select()
    .single()
  if (error) throw error
  return data
}

async function listarSetups() {
  const h = await authHeaders()
  const { data, error } = await _supabase
    .from('setups')
    .select('*')
    .order('created_at', { ascending: false })
  if (error) throw error
  return data || []
}

async function atualizarSetup(id, updates) {
  const h = await authHeaders()
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
  const h = await authHeaders()
  const { error } = await _supabase
    .from('setups')
    .delete()
    .eq('id', id)
  if (error) throw error
}

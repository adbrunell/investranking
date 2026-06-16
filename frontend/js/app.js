const REST = 'https://oaqmnaekrpukwmrxjtud.supabase.co/rest/v1'
const HEADERS = { apikey: 'sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR', Authorization: 'Bearer sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR' }

let allPrices = []
let allCotistas = []
let allDividendos = []
let fundEvents = []
let fundosDisponiveis = []
let markerFilters = { relatorio: true, relevante: true, dividendo: false, youtube: false }
let youtubeChannelFilter = [] // empty = show none until user selects
let cotSeriesFilters = { cotistas: true, cotas: true }
let divSeriesFilters = { yield: false }
let currentTicker = ''
let canvas, ctx, tooltipEl
let chartW = 0, chartH = 0
let dpr = 1

function fmtBRL(v) {
    if (v == null || isNaN(v)) return 'R$ 0,00'
    return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function fmtDateBR(d) {
    return d.toLocaleDateString('pt-BR')
}

function fmtShortDate(d) {
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
}

function fmtMonthYear(d) {
    let m = String(d.getMonth() + 1).padStart(2, '0')
    let y = String(d.getFullYear()).slice(-2)
    return m + '/' + y
}

function parseDate(s) {
    if (!s) return null
    let d = new Date(s + 'T12:00:00')
    return isNaN(d.getTime()) ? null : d
}

async function api(url) {
    let r = await fetch(url, { headers: HEADERS })
    if (!r.ok) throw new Error(r.status + ' ' + await r.text())
    return r.json()
}

async function apiAll(url) {
    let PAGE = 1000, all = []
    let r = await fetch(url + '&limit=' + PAGE, { headers: { ...HEADERS, 'Prefer': 'count=exact' } })
    if (!r.ok) throw new Error(await r.text())
    let total = 0, cr = r.headers.get('content-range')
    if (cr) { let m = cr.match(/\/(\d+)$/); if (m) total = +m[1] }
    let first = await r.json()
    all.push(...first)
    if (total > PAGE) {
        let offsets = []
        for (let i = PAGE; i < total; i += PAGE) offsets.push(i)
        for (let i = 0; i < offsets.length; i += 5) {
            let batch = offsets.slice(i, i + 5).map(o =>
                fetch(url + '&limit=' + PAGE + '&offset=' + o, { headers: HEADERS }).then(x => { if (!x.ok) throw new Error(x.status); return x.json() })
            )
            let results = await Promise.all(batch)
            results.forEach(x => all.push(...x))
        }
    }
    return all
}

async function loadFundList() {
    let rows = await api(REST + '/vw_b3_tickers?select=ticker&order=ticker.asc&limit=1000')
    let set = new Set()
    for (let r of rows) {
        if (r.ticker) set.add(r.ticker.toUpperCase())
    }
    fundosDisponiveis = [...set].sort()
    let dl = document.getElementById('fund-list')
    dl.innerHTML = fundosDisponiveis.map(t => '<option value="' + t + '">').join('')
}

function toggleMarker(el) {
    markerFilters[el.dataset.type] = el.checked
    let dataRange = document.querySelector('.btn-range.active')
    let range = parseInt(dataRange ? dataRange.dataset.range : 90)
    updateView(range)
}

function toggleYoutubePanel(e) {
    e.stopPropagation()
    let panel = document.getElementById('yt-channel-panel')
    let btn = document.getElementById('yt-channel-btn')
    if (!panel || !btn) return
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none'
    if (panel.style.display === 'block') {
        let rect = btn.getBoundingClientRect()
        panel.style.left = Math.min(rect.left, window.innerWidth - 240) + 'px'
        panel.style.top = (rect.bottom + 4) + 'px'
    }
}

function closeYoutubePanel() {
    let panel = document.getElementById('yt-channel-panel')
    if (panel) panel.style.display = 'none'
}

function onYoutubeChannelClick(el) {
    let canal = el.dataset.canal
    if (el.checked) {
        if (!youtubeChannelFilter.includes(canal)) youtubeChannelFilter.push(canal)
    } else {
        youtubeChannelFilter = youtubeChannelFilter.filter(c => c !== canal)
    }
    let label = document.getElementById('yt-channel-label')
    if (label) {
        label.textContent = youtubeChannelFilter.length > 0
            ? youtubeChannelFilter.length + ' canal' + (youtubeChannelFilter.length > 1 ? 's' : '')
            : 'Canais'
    }
    let dataRange = document.querySelector('.btn-range.active')
    let range = parseInt(dataRange ? dataRange.dataset.range : 90)
    updateView(range)
}

function populateYoutubeChannelFilter(canais) {
    let btn = document.getElementById('yt-channel-btn')
    let panel = document.getElementById('yt-channel-panel')
    if (!btn || !panel) return
    if (!canais || canais.length === 0) {
        btn.style.display = 'none'
        return
    }
    btn.style.display = 'inline-flex'
    canais = [...canais].sort((a, b) => a.localeCompare(b))
    panel.innerHTML = canais.map(c => {
        let id = 'yt-ch-' + c.replace(/\s+/g, '-').replace(/[^a-z0-9_-]/gi, '').toLowerCase()
        return '<label class="yt-channel-option" data-canal="' + c.replace(/"/g, '&quot;') + '">' +
            '<input type="checkbox" data-canal="' + c.replace(/"/g, '&quot;') + '" onchange="onYoutubeChannelClick(this)" id="' + id + '">' +
            '<span class="yt-ch-check"></span>' +
            '<span class="yt-ch-name">' + c + '</span></label>'
    }).join('')
    youtubeChannelFilter = []
    document.getElementById('yt-channel-label').textContent = 'Canais'
}

document.addEventListener('click', function (e) {
    if (!e.target.closest('#yt-channel-btn') && !e.target.closest('#yt-channel-panel')) {
        closeYoutubePanel()
    }
})

function toggleCotSeries(el) {
    cotSeriesFilters[el.dataset.series] = el.checked
    let dataRange = document.querySelector('.btn-range.active')
    let range = parseInt(dataRange ? dataRange.dataset.range : 90)
    drawCotistasChart(range)
}

function toggleDivYield(el) {
    divSeriesFilters[el.dataset.series] = el.checked
    let dataRange = document.querySelector('.btn-range.active')
    let range = parseInt(dataRange ? dataRange.dataset.range : 90)
    drawDividendChart(range)
}

function changeFund(ticker) {
    ticker = ticker.toUpperCase().trim()
    if (!ticker || ticker === currentTicker) return
    let params = new URLSearchParams(location.search)
    params.set('ticker', ticker)
    history.pushState(null, '', '?' + params.toString())
    currentTicker = ticker
    loadFund(ticker)
}

async function loadFund(ticker) {
    document.getElementById('fund-price').textContent = '—'
    document.getElementById('fund-change').innerHTML = '&nbsp;'
    allCotistas = []
    allDividendos = []
    updateCotistasStats(null)
    updatePLStats(null)

    try {
        let [priceRows, cnpjRows] = await Promise.all([
            apiAll(REST + '/b3_cotacoes_historico?select=ticker,data,fechamento,abertura,maximo,minimo,volume&ticker=eq.' + ticker + '&order=data.asc'),
            api(REST + '/fnet_tudo?select=cnpj&codigo_fundo=eq.' + ticker + '&limit=1&situacao_documento=eq.A')
        ])

        let cnpj = cnpjRows && cnpjRows.length > 0 ? cnpjRows[0].cnpj : null
        if (cnpj) {
            let cotRows = await api(REST + '/cvm_fii_complemento?select=*&cnpj_fundo_classe=eq.' + cnpj + '&order=data_informacao_numero_cotistas.asc')
            allCotistas = (cotRows || []).filter(r => r.total_numero_cotistas > 0).map(r => {
                let segs = []
                let defs = [
                    { k: 'pessoa_fisica', l: 'Pessoa Física', c: '#ffde59' },
                    { k: 'pessoa_juridica_nao_financeira', l: 'PJ Não Financeira', c: '#4285F4' },
                    { k: 'banco_comercial', l: 'Banco Comercial', c: '#34A853' },
                    { k: 'corretora_distribuidora', l: 'Corretora/Distribuidora', c: '#EA4335' },
                    { k: 'outras_pessoas_juridicas_financeira', l: 'Outras PJ Financeira', c: '#A142F4' },
                    { k: 'investidores_nao_residentes', l: 'Inv. Não Residentes', c: '#FBBC04' },
                    { k: 'entidade_aberta_previdencia_complementar', l: 'Prev. Aberta', c: '#46BDC6' },
                    { k: 'entidade_fechada_previdencia_complementar', l: 'Prev. Fechada', c: '#F9AB00' },
                    { k: 'regime_proprio_previdencia_servidores_publicos', l: 'RPPS', c: '#7BAA55' },
                    { k: 'sociedade_seguradora_resseguradora', l: 'Seguradora', c: '#E8756A' },
                    { k: 'sociedade_capitalizacao_arrendamento_mercantil', l: 'Capitalização', c: '#B0B0B0' },
                    { k: 'fii', l: 'FII', c: '#C5221F' },
                    { k: 'outros_fundos', l: 'Outros Fundos', c: '#185ABC' },
                    { k: 'distribuidores_fundo', l: 'Distribuidores', c: '#137333' },
                    { k: 'outros_tipos', l: 'Outros', c: '#D0D0D0' }
                ]
                for (let d of defs) {
                    let v = r['numero_cotistas_' + d.k]
                    if (v != null && v > 0) segs.push({ label: d.l, value: v, color: d.c })
                }
                return {
                    data: r.data_informacao_numero_cotistas,
                    dateObj: parseDate(r.data_informacao_numero_cotistas),
                    cotistas: r.total_numero_cotistas,
                    cotas: r.cotas_emitidas,
                    pl: r.patrimonio_liquido,
                    segments: segs
                }
            }).filter(r => r.dateObj != null)
        } else {
            allCotistas = []
        }

        loadFundInfo(ticker)

        if (!priceRows || priceRows.length === 0) {
            document.getElementById('last-update').textContent = 'Nenhum dado encontrado para ' + ticker
            document.getElementById('stats-grid').innerHTML = '<div class="message-container">Nenhum dado disponível para este fundo.</div>'
            drawChart([])
            drawPLChart(365)
            updateCotistasStats(null)
            drawDividendChart(365)
            return
        }
        allPrices = priceRows.map(r => ({
            ticker: r.ticker,
            data: r.data,
            dateObj: parseDate(r.data),
            fechamento: r.fechamento,
            abertura: r.abertura,
            maximo: r.maximo,
            minimo: r.minimo,
            volume: r.volume
        })).filter(p => p.dateObj != null)

        let dataRange = document.querySelector('.btn-range.active')
        let range = parseInt(dataRange ? dataRange.dataset.range : 90)
        updateView(range)
        document.getElementById('last-update').textContent = allPrices.length + ' pregões — ' + fmtDateBR(allPrices[0].dateObj) + ' até ' + fmtDateBR(allPrices[allPrices.length - 1].dateObj)
    } catch (e) {
        console.error(e)
        document.getElementById('last-update').textContent = 'Erro ao carregar dados'
    }
}

function norm(s) {
    return s ? s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim() : ''
}

async function loadFundInfo(ticker) {
    fundEvents = []

    try {
        let SIT = '&situacao_documento=eq.A'
        let [nomeRows, rendRows, relRows, fatRows, sdRows] = await Promise.all([
            api(REST + '/fnet_tudo?select=nome_fundo_documento&codigo_fundo=eq.' + ticker + '&limit=1' + SIT),
            api(REST + '/fnet_tudo?select=data_entrega,tipo,rendimento&codigo_fundo=eq.' + ticker + '&tipo_documento=like.*Rendimentos*&tipo=neq.' + SIT + '&order=data_entrega.desc'),
            api(REST + '/fnet_tudo?select=data_entrega,tipo_documento,link_visualizar&codigo_fundo=eq.' + ticker + '&categoria_documento=like.*Relat*rio*' + SIT + '&order=data_entrega.desc'),
            api(REST + '/fnet_tudo?select=data_entrega,tipo_documento,link_visualizar&codigo_fundo=eq.' + ticker + '&categoria_documento=like.*Fato*' + SIT + '&order=data_entrega.desc'),
        ])

        let all = []
        for (let r of (relRows || [])) {
            let dt = r.data_entrega ? r.data_entrega.split('T')[0] : null
            if (dt && r.link_visualizar) {
                all.push({
                    data: dt, tipo: 'relatorio',
                    subtipo: r.tipo_documento || 'Documento',
                    link: r.link_visualizar, isRelevante: false
                })
            }
        }
        for (let r of (fatRows || [])) {
            let dt = r.data_entrega ? r.data_entrega.split('T')[0] : null
            if (dt && r.link_visualizar) {
                all.push({
                    data: dt, tipo: 'relevante',
                    subtipo: r.tipo_documento || 'Fato Relevante',
                    link: r.link_visualizar, isRelevante: true
                })
            }
        }
        for (let r of (rendRows || [])) {
            let dt = r.data_entrega ? r.data_entrega.split('T')[0] : null
            if (dt) {
                all.push({
                    data: dt,
                    tipo: 'dividendo',
                    subtipo: r.tipo || 'Dividendo',
                    valor: r.rendimento || null,
                    link: null
                })
            }
        }
        // YouTube videos
        try {
            let ytRows = await api(REST + '/youtube_videos?select=video_id,ticker,titulo,canal,publicacao,link&ticker=eq.' + ticker + '&order=publicacao.desc')
            let canais = [...new Set((ytRows || []).map(v => v.canal).filter(Boolean))]
            populateYoutubeChannelFilter(canais)
            if (ytRows && ytRows.length > 0) {
                for (let v of ytRows) {
                    let dt = v.publicacao ? v.publicacao.split('T')[0] : null
                    if (dt) {
                        all.push({
                            data: dt,
                            tipo: 'youtube',
                            subtipo: v.titulo,
                            canal: v.canal,
                            link: v.link,
                            videoId: v.video_id
                        })
                    }
                }
            }
        } catch (e) {}
        fundEvents = all

        allDividendos = (rendRows || []).filter(r => r.rendimento != null && r.data_entrega).map(r => {
            let dt = r.data_entrega.split('T')[0]
            return { data: dt, dateObj: parseDate(dt), valor: parseFloat(r.rendimento) }
        }).filter(d => d.dateObj != null && d.valor > 0).sort((a, b) => a.dateObj - b.dateObj)

        let dataRange = document.querySelector('.btn-range.active')
        let range = parseInt(dataRange ? dataRange.dataset.range : 90)
        updateView(range)
    } catch (e) {
        console.error('Erro ao carregar info do fundo:', e)
    }
}

function updateView(rangeDays) {
    let filtered = allPrices
    if (rangeDays > 0) {
        let cutoff = new Date()
        cutoff.setDate(cutoff.getDate() - rangeDays)
        filtered = allPrices.filter(p => p.dateObj >= cutoff)
    }
    if (filtered.length < 2) {
        filtered = allPrices
    }
    updateStats(filtered)
    drawChart(filtered)
    drawCotistasChart(rangeDays)
    drawPLChart(rangeDays)
    drawDividendChart(rangeDays)
}

function updateStats(data) {
    if (!data || data.length < 2) {
        document.querySelectorAll('#stats-grid .stat-value').forEach(el => el.textContent = '—')
        return
    }
    let closes = data.map(d => d.fechamento).filter(v => v != null)
    let volumes = data.map(d => d.volume).filter(v => v != null)
    let min = Math.min(...closes)
    let max = Math.max(...closes)
    let first = closes[0]
    let last = closes[closes.length - 1]
    let change = first !== 0 ? ((last - first) / first) * 100 : 0
    let avgVol = volumes.length > 0 ? volumes.reduce((a, b) => a + b, 0) / volumes.length : 0

    document.getElementById('stat-min').textContent = fmtBRL(min)
    document.getElementById('stat-max').textContent = fmtBRL(max)
    let varEl = document.getElementById('stat-var')
    varEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%'
    varEl.className = 'stat-value ' + (change >= 0 ? 'positive' : 'negative')
    document.getElementById('stat-vol').textContent = avgVol.toLocaleString('pt-BR', { maximumFractionDigits: 0 })

    let lastRow = data[data.length - 1]
    let lastPrice = lastRow.fechamento
    document.getElementById('fund-price').textContent = fmtBRL(lastPrice)

    let prevPrice = data.length > 1 ? data[data.length - 2].fechamento : lastPrice
    let dayChangePct = prevPrice !== 0 ? ((lastPrice - prevPrice) / prevPrice) * 100 : 0
    let chEl = document.getElementById('fund-change')
    let chStr = (dayChangePct >= 0 ? '+' : '') + dayChangePct.toFixed(2) + '%'
    chEl.textContent = chStr
    chEl.className = 'fund-price-change ' + (dayChangePct >= 0 ? 'positive' : 'negative')
}

function updateCotistasStats(cotistas) {
    let cotVal = document.getElementById('cot-stat-cotistas')
    let cotCresc = document.getElementById('cot-stat-cresc-cot')
    let cVal = document.getElementById('cot-stat-cotas')
    let cCresc = document.getElementById('cot-stat-cresc-cotas')
    if (!cotistas || cotistas.length < 2) {
        if (cotVal) cotVal.textContent = '—'
        if (cotCresc) { cotCresc.textContent = ''; cotCresc.className = 'stat-value' }
        if (cVal) cVal.textContent = '—'
        if (cCresc) { cCresc.textContent = ''; cCresc.className = 'stat-value' }
        return
    }
    let last = cotistas[cotistas.length - 1]
    let first = cotistas[0]
    let cotistasPct = first.cotistas !== 0 ? ((last.cotistas - first.cotistas) / first.cotistas) * 100 : 0
    if (cotVal) cotVal.textContent = Math.round(last.cotistas).toLocaleString('pt-BR')
    if (cotCresc) {
        cotCresc.textContent = (cotistasPct >= 0 ? '+' : '') + cotistasPct.toFixed(2) + '%'
        cotCresc.className = 'stat-value ' + (cotistasPct >= 0 ? 'positive' : 'negative')
    }
    let cotasData = cotistas.filter(c => c.cotas != null && c.cotas > 0)
    if (cotasData.length > 0) {
        let lastC = cotasData[cotasData.length - 1]
        if (cVal) {
            let label = lastC.cotas >= 1000000 ? (lastC.cotas / 1000000).toFixed(2) + 'M' :
                lastC.cotas >= 1000 ? (lastC.cotas / 1000).toFixed(0) + 'K' :
                    Math.round(lastC.cotas).toLocaleString('pt-BR')
            cVal.textContent = label
        }
        if (cotasData.length >= 2 && cCresc) {
            let firstC = cotasData[0]
            let lastC2 = cotasData[cotasData.length - 1]
            let cotasPct = firstC.cotas !== 0 ? ((lastC2.cotas - firstC.cotas) / firstC.cotas) * 100 : 0
            cCresc.textContent = (cotasPct >= 0 ? '+' : '') + cotasPct.toFixed(2) + '%'
            cCresc.className = 'stat-value ' + (cotasPct >= 0 ? 'positive' : 'negative')
        }
    } else {
        if (cVal) cVal.textContent = '—'
        if (cCresc) { cCresc.textContent = ''; cCresc.className = 'stat-value' }
    }
}

function updatePLStats(data) {
    let elAtual = document.getElementById('pl-stat-atual')
    let elVar = document.getElementById('pl-stat-var')
    let elData = document.getElementById('pl-stat-data')
    if (!data || data.length < 2) {
        if (elAtual) elAtual.textContent = '—'
        if (elVar) { elVar.textContent = '—'; elVar.className = 'stat-value' }
        if (elData) elData.textContent = '—'
        return
    }
    let first = data[0]
    let last = data[data.length - 1]
    let pct = first.pl !== 0 ? ((last.pl - first.pl) / first.pl) * 100 : 0
    if (elAtual) elAtual.textContent = fmtBRL(last.pl)
    if (elVar) {
        elVar.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'
        elVar.className = 'stat-value ' + (pct >= 0 ? 'positive' : 'negative')
    }
    if (elData) elData.textContent = fmtDateBR(last.dateObj)
}

function drawPLChart(rangeDays) {
    let canvas = document.getElementById('chart-pl')
    if (!canvas) return
    let ctx = canvas.getContext('2d')
    let rect = canvas.parentElement.getBoundingClientRect()
    let w = rect.width - 40
    let h = 200
    let dpr = window.devicePixelRatio || 1
    canvas.style.width = w + 'px'
    canvas.style.height = h + 'px'
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, w, h)

    if (!allCotistas || allCotistas.length < 2) {
        updatePLStats(null)
        return
    }

    let cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - rangeDays)
    let plData = rangeDays > 0 ? allCotistas.filter(c => c.dateObj >= cutoff && c.pl != null && c.pl > 0) : allCotistas.filter(c => c.pl != null && c.pl > 0)
    if (plData.length < 2) {
        updatePLStats(null)
        ctx.font = '13px system-ui, sans-serif'
        ctx.fillStyle = '#888'
        ctx.textAlign = 'center'
        ctx.fillText('Dados de PL insuficientes para o período', w / 2, 50)
        return
    }

    updatePLStats(plData)

    let pad = { top: 20, right: 10, bottom: 35, left: 10 }
    let pW = w - pad.left - pad.right
    let pH = h - pad.top - pad.bottom

    let vals = plData.map(c => c.pl)
    let vMin = Math.min(...vals) * 0.95
    let vMax = Math.max(...vals) * 1.05
    let vRange = vMax - vMin || 1
    function yPos(v) { return pad.top + pH - ((v - vMin) / vRange) * pH }
    let yBot = pad.top + pH

    ctx.strokeStyle = '#2a2b2d'
    ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
        let y = pad.top + (i / 4) * pH
        ctx.beginPath()
        ctx.moveTo(pad.left, y)
        ctx.lineTo(w - pad.right, y)
        ctx.stroke()
    }

    let step = pW / plData.length

    for (let i = 0; i < plData.length; i++) {
        let pt = plData[i]
        pt._x = pad.left + (i + 0.5) * step
        pt._y = yPos(pt.pl)
    }

    ctx.beginPath()
    for (let i = 0; i < plData.length; i++) {
        let pt = plData[i]
        if (pt.pl > 0) {
            if (i === 0 || !plData[i - 1].pl) ctx.moveTo(pt._x, pt._y)
            else ctx.lineTo(pt._x, pt._y)
        }
    }
    ctx.strokeStyle = '#a78bfa'
    ctx.lineWidth = 2
    ctx.stroke()

    let firstIdx = plData.findIndex(p => p.pl > 0)
    let lastIdx = plData.length - 1 - [...plData].reverse().findIndex(p => p.pl > 0)
    if (firstIdx >= 0 && lastIdx >= 0) {
        ctx.beginPath()
        ctx.moveTo(plData[firstIdx]._x, plData[firstIdx]._y)
        for (let i = firstIdx + 1; i <= lastIdx; i++) {
            if (plData[i].pl > 0) ctx.lineTo(plData[i]._x, plData[i]._y)
        }
        ctx.lineTo(plData[lastIdx]._x, yBot)
        ctx.lineTo(plData[firstIdx]._x, yBot)
        ctx.closePath()
        ctx.fillStyle = 'rgba(167,139,250,0.1)'
        ctx.fill()
    }

    for (let i = 0; i < plData.length; i++) {
        let pt = plData[i]
        ctx.beginPath()
        ctx.arc(pt._x, pt._y, 3, 0, Math.PI * 2)
        ctx.fillStyle = '#a78bfa'
        ctx.fill()
        let label = pt.pl >= 1000000 ? (pt.pl / 1000000).toFixed(1) + 'M' :
            pt.pl >= 1000 ? (pt.pl / 1000).toFixed(1) + 'K' :
                Math.round(pt.pl).toLocaleString('pt-BR')
        ctx.fillStyle = '#a78bfa'
        ctx.font = 'bold 11px system-ui, sans-serif'
        ctx.textAlign = 'center'
        let labelY = pt._y - 10
        if (labelY < 10) labelY = 10
        ctx.fillText(label, pt._x, labelY)
    }

    ctx.textAlign = 'center'
    ctx.fillStyle = '#888'
    ctx.font = '10px system-ui, sans-serif'
    let maxLabels = Math.floor(pW / 55)
    let mStep = Math.max(1, Math.floor(plData.length / maxLabels))
    for (let i = 0; i < plData.length; i += mStep) {
        ctx.fillText(fmtMonthYear(plData[i].dateObj), plData[i]._x, h - pad.bottom + 16)
    }

    canvas._plData = plData
    canvas._plW = w
    canvas._plH = h
    canvas._plPad = pad
    canvas._plStep = step
    canvas._plLen = plData.length

    let overlay = document.getElementById('chart-pl-overlay')
    if (overlay) {
        let octx = overlay.getContext('2d')
        let dpr2 = window.devicePixelRatio || 1
        overlay.style.width = w + 'px'
        overlay.style.height = h + 'px'
        overlay.width = w * dpr2
        overlay.height = h * dpr2
        octx.setTransform(dpr2, 0, 0, dpr2, 0, 0)
        octx.clearRect(0, 0, w, h)
    }
}

function drawPLOverlay(cx, cy, plW, plH) {
    let overlay = document.getElementById('chart-pl-overlay')
    if (!overlay) return
    let octx = overlay.getContext('2d')
    let dpr = window.devicePixelRatio || 1
    octx.setTransform(dpr, 0, 0, dpr, 0, 0)
    octx.clearRect(0, 0, plW, plH)

    if (cx < 0) return
    octx.strokeStyle = 'rgba(255, 255, 255, 0.25)'
    octx.lineWidth = 1
    octx.setLineDash([4, 4])
    octx.beginPath()
    octx.moveTo(cx, 0)
    octx.lineTo(cx, plH)
    octx.stroke()
    octx.setLineDash([])
}

function updateDividendStats(data) {
    let elUltimo = document.getElementById('div-stat-ultimo')
    let elUltYield = document.getElementById('div-stat-ult-yield')
    let elTotal = document.getElementById('div-stat-total')
    let elTotalYield = document.getElementById('div-stat-total-yield')
    let elCagr = document.getElementById('div-stat-cagr')
    let elLabelCagr = document.getElementById('div-label-cagr')
    if (!data || data.length < 2) {
        if (elUltimo) elUltimo.textContent = '—'
        if (elUltYield) elUltYield.textContent = '—'
        if (elTotal) elTotal.textContent = '—'
        if (elTotalYield) elTotalYield.textContent = '—'
        if (elCagr) { elCagr.textContent = '—'; elCagr.className = 'stat-value' }
        if (elLabelCagr) elLabelCagr.textContent = 'CAGR'
        return
    }
    let vals = data.map(d => d.valor)
    let yields = data.map(d => d._yield).filter(y => y != null)
    let ultimo = vals[vals.length - 1]
    let ultYield = data[data.length - 1]._yield
    let total = vals.reduce((a, b) => a + b, 0)
    let totalYield = yields.length > 0 ? yields.reduce((a, b) => a + b, 0) : null
    if (elLabelCagr) {
        let months = Math.round((data[data.length - 1].dateObj - data[0].dateObj) / (30.44 * 24 * 60 * 60 * 1000))
        elLabelCagr.textContent = 'CAGR (' + months + 'M)'
    }
    if (elUltimo) elUltimo.textContent = fmtBRL(ultimo)
    if (elUltYield) {
        elUltYield.textContent = ultYield != null ? ultYield.toFixed(2) + '%' : '—'
        elUltYield.className = 'stat-value' + (ultYield != null && ultYield >= 0 ? ' positive' : '')
    }
    if (elTotal) elTotal.textContent = fmtBRL(total)
    if (elTotalYield) {
        elTotalYield.textContent = totalYield != null ? totalYield.toFixed(2) + '%' : '—'
        elTotalYield.className = 'stat-value' + (totalYield != null && totalYield >= 0 ? ' positive' : '')
    }
    if (elCagr) {
        let cagr = calcCAGR(data)
        if (cagr != null) {
            elCagr.textContent = (cagr >= 0 ? '+' : '') + cagr.toFixed(2) + '%'
            elCagr.className = 'stat-value ' + (cagr >= 0 ? 'positive' : 'negative')
        } else {
            elCagr.textContent = '—'
            elCagr.className = 'stat-value'
        }
    }
}

function calcCAGR(data) {
    if (!data || data.length < 2) return null
    let first = data[0]
    let last = data[data.length - 1]
    if (first.valor <= 0 || last.valor <= 0) return null
    let years = (last.dateObj - first.dateObj) / (365.25 * 24 * 60 * 60 * 1000)
    if (years < 0.5) return null
    return (Math.pow(last.valor / first.valor, 1 / years) - 1) * 100
}

function drawDividendChart(rangeDays) {
    let canvas = document.getElementById('chart-dividendos')
    if (!canvas) return
    let ctx = canvas.getContext('2d')
    let rect = canvas.parentElement.getBoundingClientRect()
    let w = rect.width - 40
    let h = 200
    let dpr = window.devicePixelRatio || 1
    canvas.style.width = w + 'px'
    canvas.style.height = h + 'px'
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, w, h)

    if (!allDividendos || allDividendos.length < 2) {
        updateDividendStats(null)
        ctx.font = '13px system-ui, sans-serif'
        ctx.fillStyle = '#888'
        ctx.textAlign = 'center'
        ctx.fillText('Dados de dividendos insuficientes', w / 2, 50)
        return
    }

    let cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - rangeDays)
    let divData = rangeDays > 0 ? allDividendos.filter(d => d.dateObj >= cutoff) : allDividendos.slice()
    if (divData.length < 2) {
        updateDividendStats(null)
        ctx.font = '13px system-ui, sans-serif'
        ctx.fillStyle = '#888'
        ctx.textAlign = 'center'
        ctx.fillText('Dados de dividendos insuficientes para o per\u00edodo', w / 2, 50)
        return
    }

    updateDividendStats(divData)

    let showYield = divSeriesFilters.yield
    let pad = { top: 20, right: 10, bottom: 35, left: 10 }
    let pW = w - pad.left - pad.right
    let pH = h - pad.top - pad.bottom

    let vals = divData.map(d => d.valor)
    let vMin = Math.min(...vals) * 0.95
    let vMax = Math.max(...vals) * 1.05
    let vRange = vMax - vMin || 1
    function yPos(v) { return pad.top + pH - ((v - vMin) / vRange) * pH }
    let yBot = pad.top + pH

    if (showYield) {
        let yields = divData.filter(d => d._yield != null).map(d => d._yield)
        let yMin = yields.length > 0 ? Math.min(...yields) * 0.9 : 0
        let yMax = yields.length > 0 ? Math.max(...yields) * 1.1 : 1
        let yRange = yMax - yMin || 1
        for (let i = 0; i < divData.length; i++) {
            divData[i]._yieldPos = divData[i]._yield != null
                ? pad.top + pH - ((divData[i]._yield - yMin) / yRange) * pH
                : null
        }
    }

    ctx.strokeStyle = '#2a2b2d'
    ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
        let y = pad.top + (i / 4) * pH
        ctx.beginPath()
        ctx.moveTo(pad.left, y)
        ctx.lineTo(w - pad.right, y)
        ctx.stroke()
    }

    let step = pW / divData.length

    for (let i = 0; i < divData.length; i++) {
        let pt = divData[i]
        pt._x = pad.left + (i + 0.5) * step
        pt._y = yPos(pt.valor)
    }

    ctx.beginPath()
    for (let i = 0; i < divData.length; i++) {
        let pt = divData[i]
        if (i === 0) ctx.moveTo(pt._x, pt._y)
        else ctx.lineTo(pt._x, pt._y)
    }
    ctx.strokeStyle = '#81c995'
    ctx.lineWidth = 2
    ctx.stroke()

    let firstIdx = 0
    let lastIdx = divData.length - 1
    ctx.beginPath()
    ctx.moveTo(divData[firstIdx]._x, divData[firstIdx]._y)
    for (let i = firstIdx + 1; i <= lastIdx; i++) {
        ctx.lineTo(divData[i]._x, divData[i]._y)
    }
    ctx.lineTo(divData[lastIdx]._x, yBot)
    ctx.lineTo(divData[firstIdx]._x, yBot)
    ctx.closePath()
    ctx.fillStyle = 'rgba(129,201,149,0.1)'
    ctx.fill()

    for (let i = 0; i < divData.length; i++) {
        let pt = divData[i]
        ctx.beginPath()
        ctx.arc(pt._x, pt._y, 3, 0, Math.PI * 2)
        ctx.fillStyle = '#81c995'
        ctx.fill()
        let label = fmtBRL(pt.valor)
        ctx.fillStyle = '#81c995'
        ctx.font = 'bold 11px system-ui, sans-serif'
        ctx.textAlign = 'center'
        let labelY = pt._y - 10
        if (labelY < 10) labelY = 10
        ctx.fillText(label, pt._x, labelY)
    }

    if (showYield) {
        ctx.beginPath()
        for (let i = 0; i < divData.length; i++) {
            let pt = divData[i]
            if (pt._yieldPos != null) {
                if (i === 0 || divData[i - 1]._yieldPos === null) ctx.moveTo(pt._x, pt._yieldPos)
                else ctx.lineTo(pt._x, pt._yieldPos)
            }
        }
        ctx.strokeStyle = '#4285F4'
        ctx.lineWidth = 2
        ctx.stroke()

        for (let i = 0; i < divData.length; i++) {
            let pt = divData[i]
            if (pt._yieldPos != null) {
                ctx.beginPath()
                ctx.arc(pt._x, pt._yieldPos, 3, 0, Math.PI * 2)
                ctx.fillStyle = '#4285F4'
                ctx.fill()
                ctx.fillStyle = '#4285F4'
                ctx.font = 'bold 10px system-ui, sans-serif'
                ctx.textAlign = 'center'
                let ly = pt._yieldPos - 10
                if (ly < 10) ly = 10
                ctx.fillText(pt._yield.toFixed(2) + '%', pt._x, ly)
            }
        }
    }

    ctx.textAlign = 'center'
    ctx.fillStyle = '#888'
    ctx.font = '10px system-ui, sans-serif'
    let maxLabels = Math.floor(pW / 55)
    let mStep = Math.max(1, Math.floor(divData.length / maxLabels))
    for (let i = 0; i < divData.length; i += mStep) {
        ctx.fillText(fmtMonthYear(divData[i].dateObj), divData[i]._x, h - pad.bottom + 16)
    }
}

function drawChart(data) {
    canvas = document.getElementById('chart')
    ctx = canvas.getContext('2d')
    dpr = window.devicePixelRatio || 1
    let rect = canvas.parentElement.getBoundingClientRect()
    chartW = rect.width - 40
    chartH = 338
    canvas.style.width = chartW + 'px'
    canvas.style.height = chartH + 'px'
    canvas.width = chartW * dpr
    canvas.height = chartH * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, chartW, chartH)

    let overlay = document.getElementById('chart-overlay')
    overlay.style.width = chartW + 'px'
    overlay.style.height = chartH + 'px'
    overlay.width = chartW * dpr
    overlay.height = chartH * dpr
    let octx = overlay.getContext('2d')
    octx.scale(dpr, dpr)
    octx.clearRect(0, 0, chartW, chartH)

    if (!data || data.length < 2) {
        ctx.fillStyle = '#b4b4b4'
        ctx.font = '14px system-ui, sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('Dados insuficientes para exibir o gráfico', chartW / 2, chartH / 2)
        return
    }

    let pad = { top: 20, right: 50, bottom: 35, left: 60 }
    let pW = chartW - pad.left - pad.right
    let chartH_full = chartH - pad.top - pad.bottom

    let closes = data.map(d => d.fechamento)
    let min = Math.min(...closes)
    let max = Math.max(...closes)
    let range = max - min
    if (range === 0) range = 1
    let padding = range * 0.05
    let yMin = min - padding
    let yMax = max + padding

    let volumes = data.map(d => d.volume != null ? d.volume : 0)
    let volMax = Math.max(...volumes)

    function xPos(i) { return pad.left + (i / (data.length - 1)) * pW }
    function yPos(v) { return pad.top + chartH_full - ((v - yMin) / (yMax - yMin)) * chartH_full }

    // Grid + eixo esquerdo (preço)
    ctx.strokeStyle = '#2a2b2d'
    ctx.lineWidth = 1
    let gridCount = 4
    for (let i = 0; i <= gridCount; i++) {
        let y = pad.top + (i / gridCount) * chartH_full
        ctx.beginPath()
        ctx.moveTo(pad.left, y)
        ctx.lineTo(chartW - pad.right, y)
        ctx.stroke()
        let val = yMax - ((y - pad.top) / chartH_full) * (yMax - yMin)
        ctx.fillStyle = '#888'
        ctx.font = '11px system-ui, sans-serif'
        ctx.textAlign = 'right'
        ctx.fillText(fmtBRL(val), pad.left - 8, y + 4)
    }

    // Barras de volume no eixo direito (azul Gemini #4285F4)
    if (volMax > 0) {
        let volPad = volMax * 0.50
        let volMaxPad = volMax + volPad
        let barW = pW / data.length
        for (let i = 0; i < data.length; i++) {
            if (volumes[i] <= 0) continue
            let barH = (volumes[i] / volMaxPad) * chartH_full
            let x = xPos(i) - barW * 0.35
            let y = pad.top + chartH_full - barH
            ctx.fillStyle = '#4285F4'
            ctx.fillRect(x, y, Math.max(barW * 0.7, 1), barH)
        }
        // Labels do eixo direito removidos
    }

    // Linha de preço (sem hachurado)
    ctx.beginPath()
    for (let i = 0; i < data.length; i++) {
        let x = xPos(i)
        let y = yPos(data[i].fechamento)
        if (i === 0) ctx.moveTo(x, y)
        else {
            let prevX = xPos(i - 1)
            let prevY = yPos(data[i - 1].fechamento)
            let cpx = (prevX + x) / 2
            ctx.bezierCurveTo(cpx, prevY, cpx, y, x, y)
        }
    }
    ctx.strokeStyle = '#ffde59'
    ctx.lineWidth = 2
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    ctx.stroke()

    ctx.textAlign = 'center'
    ctx.fillStyle = '#888'
    ctx.font = '10px system-ui, sans-serif'
    let labelCount = 6
    for (let i = 0; i < labelCount; i++) {
        let idx = Math.round((i / (labelCount - 1)) * (data.length - 1))
        let x = xPos(idx)
        ctx.fillText(fmtShortDate(data[idx].dateObj), x, chartH - pad.bottom + 16)
    }

    let markerData = []
    let dataMin = data[0].dateObj
    let dataMax = data[data.length - 1].dateObj
    let markerColors = { relatorio: '#4285F4', relevante: '#ffde59', dividendo: '#81c995', youtube: '#FF0000' }
    for (let evt of fundEvents) {
        let tipo = evt.tipo
        if (!markerFilters[tipo]) continue
        // Channel filter for YouTube
        if (tipo === 'youtube' && !youtubeChannelFilter.includes(evt.canal)) continue
        let ed = parseDate(evt.data)
        if (!ed || ed < dataMin || ed > dataMax) continue
        let idx = -1
        let minDiff = Infinity
        for (let i = 0; i < data.length; i++) {
            let diff = Math.abs(data[i].dateObj - ed)
            if (diff < minDiff) { minDiff = diff; idx = i }
        }
        if (idx < 0 || minDiff > 86400000 * 3) continue
        let mx = xPos(idx)
        let my = pad.top - 2
        let color = markerColors[tipo] || '#999'

        let py = yPos(data[idx].fechamento)
        ctx.save()
        ctx.setLineDash([3, 4])
        ctx.strokeStyle = color + '55'
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(mx, my + 10)
        ctx.lineTo(mx, py)
        ctx.stroke()
        ctx.restore()

        let iconMap = { relatorio: 'R', relevante: '!', dividendo: '$', youtube: '' }
        let icon = iconMap[tipo] || '?'
        let cx = mx + 1, cy = my + 2
        ctx.save()
        ctx.beginPath()
        ctx.arc(cx, cy, 10, 0, Math.PI * 2)
        ctx.fillStyle = '#131314'
        ctx.fill()
        ctx.strokeStyle = color
        ctx.lineWidth = 2
        ctx.stroke()
        if (tipo === 'youtube') {
            // Draw play triangle inside
            ctx.beginPath()
            let s = 5, sx = cx - 1
            ctx.moveTo(sx - s * 0.35, cy - s * 0.5)
            ctx.lineTo(sx - s * 0.35, cy + s * 0.5)
            ctx.lineTo(sx + s * 0.5, cy)
            ctx.closePath()
            ctx.fillStyle = color
            ctx.fill()
        } else {
            ctx.font = tipo === 'relevante' ? 'bold 15px system-ui, sans-serif' : '16px system-ui, sans-serif'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillStyle = color
            ctx.fillText(icon, cx, cy + 1)
        }
        ctx.restore()

        markerData.push({ x: mx, idx: idx, link: evt.link, tipo: tipo, subtipo: evt.subtipo, valor: evt.valor })
    }

    canvas._chartData = data
    canvas._xPos = xPos
    canvas._yPos = yPos
    canvas._markerData = markerData
    clearOverlay()
}

let overlayCtx = null

function drawOverlay(cx, cy) {
    if (!overlayCtx) overlayCtx = document.getElementById('chart-overlay').getContext('2d')
    overlayCtx.clearRect(0, 0, chartW, chartH)
    overlayCtx.strokeStyle = 'rgba(255, 255, 255, 0.25)'
    overlayCtx.lineWidth = 1
    overlayCtx.setLineDash([4, 4])
    overlayCtx.beginPath()
    overlayCtx.moveTo(cx, 0)
    overlayCtx.lineTo(cx, chartH)
    overlayCtx.stroke()
    overlayCtx.setLineDash([])
    overlayCtx.beginPath()
    overlayCtx.arc(cx, cy, 5, 0, Math.PI * 2)
    overlayCtx.fillStyle = '#ffde59'
    overlayCtx.fill()
    overlayCtx.strokeStyle = '#131314'
    overlayCtx.lineWidth = 2
    overlayCtx.stroke()
}

function drawCotistasChart(rangeDays) {
    let canvas = document.getElementById('chart-cotistas')
    if (!canvas) return
    let ctx2 = canvas.getContext('2d')
    let rect = canvas.parentElement.getBoundingClientRect()
    let w = rect.width - 40
    let h = 200
    let dpr2 = window.devicePixelRatio || 1
    canvas.style.width = w + 'px'
    canvas.style.height = h + 'px'
    canvas.width = w * dpr2
    canvas.height = h * dpr2
    ctx2.scale(dpr2, dpr2)
    ctx2.clearRect(0, 0, w, h)

    if (!allCotistas || allCotistas.length < 2) {
        updateCotistasStats(null)
        return
    }

    let cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - rangeDays)
    let cotistas = rangeDays > 0 ? allCotistas.filter(c => c.dateObj >= cutoff) : allCotistas.slice()
    if (cotistas.length < 2) {
        updateCotistasStats(null)
        ctx2.font = '13px system-ui, sans-serif'
        ctx2.fillStyle = '#888'
        ctx2.textAlign = 'center'
        ctx2.fillText('Dados mensais de cotistas — use um período maior', w / 2, 50)
        return
    }

    updateCotistasStats(cotistas)

    let pad = { top: 20, right: 10, bottom: 35, left: 60 }
    let pW = w - pad.left - pad.right
    let pH = h - pad.top - pad.bottom

    let cistas = cotistas.filter(c => c.cotistas > 0).map(c => c.cotistas)
    let istasMin = cistas.length > 0 ? Math.min(...cistas) * 0.95 : 0
    let istasMax = cistas.length > 0 ? Math.max(...cistas) * 1.05 : 1
    let istasRange = istasMax - istasMin || 1
    function yPos(v) { return pad.top + pH - ((v - istasMin) / istasRange) * pH }
    let yBot = pad.top + pH

    let cotas = cotistas.filter(c => c.cotas != null && c.cotas > 0).map(c => c.cotas)
    let cotasMin = cotas.length > 0 ? Math.min(...cotas) * 0.95 : 0
    let cotasMax = cotas.length > 0 ? Math.max(...cotas) * 1.05 : 1
    let cotasRange = cotasMax - cotasMin || 1
    function cPos(v) { return pad.top + pH - ((v - cotasMin) / cotasRange) * pH }

    ctx2.strokeStyle = '#2a2b2d'
    ctx2.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
        let y = pad.top + (i / 4) * pH
        ctx2.beginPath()
        ctx2.moveTo(pad.left, y)
        ctx2.lineTo(w - pad.right, y)
        ctx2.stroke()
    }

    let step = pW / cotistas.length

    for (let i = 0; i < cotistas.length; i++) {
        let pt = cotistas[i]
        let cx = pad.left + (i + 0.5) * step
        pt._x = cx
        pt._y = pt.cotistas > 0 ? yPos(pt.cotistas) : null
        pt._cy = pt.cotas > 0 ? cPos(pt.cotas) : null
    }

    ctx2.beginPath()
    for (let i = 0; i < cotistas.length; i++) {
        let pt = cotistas[i]
        if (pt._y !== null) {
            if (i === 0 || cotistas[i - 1]._y === null) ctx2.moveTo(pt._x, pt._y)
            else ctx2.lineTo(pt._x, pt._y)
        }
    }
    ctx2.strokeStyle = '#ffde59'
    ctx2.lineWidth = 2
    ctx2.stroke()

    let firstIdx = cotistas.findIndex(p => p._y !== null)
    let lastIdx = cotistas.length - 1 - [...cotistas].reverse().findIndex(p => p._y !== null)
    if (firstIdx >= 0 && lastIdx >= 0) {
        ctx2.beginPath()
        ctx2.moveTo(cotistas[firstIdx]._x, cotistas[firstIdx]._y)
        for (let i = firstIdx + 1; i <= lastIdx; i++) {
            if (cotistas[i]._y !== null) ctx2.lineTo(cotistas[i]._x, cotistas[i]._y)
        }
        ctx2.lineTo(cotistas[lastIdx]._x, yBot)
        ctx2.lineTo(cotistas[firstIdx]._x, yBot)
        ctx2.closePath()
        ctx2.fillStyle = 'rgba(255,222,89,0.1)'
        ctx2.fill()
    }

    if (cotSeriesFilters.cotas) {
        let cBot = pad.top + pH
        ctx2.beginPath()
        for (let i = 0; i < cotistas.length; i++) {
            let pt = cotistas[i]
            if (pt._cy !== null) {
                if (i === 0 || cotistas[i - 1]._cy === null) ctx2.moveTo(pt._x, pt._cy)
                else ctx2.lineTo(pt._x, pt._cy)
            }
        }
        ctx2.strokeStyle = '#4285F4'
        ctx2.lineWidth = 2
        ctx2.stroke()
        let cFirst = cotistas.findIndex(p => p._cy !== null)
        let cLast = cotistas.length - 1 - [...cotistas].reverse().findIndex(p => p._cy !== null)
        if (cFirst >= 0 && cLast >= 0) {
            ctx2.beginPath()
            ctx2.moveTo(cotistas[cFirst]._x, cotistas[cFirst]._cy)
            for (let i = cFirst + 1; i <= cLast; i++) {
                if (cotistas[i]._cy !== null) ctx2.lineTo(cotistas[i]._x, cotistas[i]._cy)
            }
            ctx2.lineTo(cotistas[cLast]._x, cBot)
            ctx2.lineTo(cotistas[cFirst]._x, cBot)
            ctx2.closePath()
            ctx2.fillStyle = 'rgba(66,133,244,0.1)'
            ctx2.fill()
        }
    }

    for (let i = 0; i < cotistas.length; i++) {
        let pt = cotistas[i]
        if (pt._y !== null) {
            ctx2.beginPath()
            ctx2.arc(pt._x, pt._y, 3, 0, Math.PI * 2)
            ctx2.fillStyle = '#ffde59'
            ctx2.fill()
            let cLabel1 = pt.cotistas >= 1000000 ? (pt.cotistas / 1000000).toFixed(1) + 'M' :
                pt.cotistas >= 1000 ? (pt.cotistas / 1000).toFixed(1) + 'K' :
                    Math.round(pt.cotistas).toLocaleString('pt-BR')
            ctx2.fillText(cLabel1, pt._x, Math.max(pt._y - 10, 10))
        }
        if (pt._cy !== null && cotSeriesFilters.cotas) {
            ctx2.beginPath()
            ctx2.arc(pt._x, pt._cy, 3, 0, Math.PI * 2)
            ctx2.fillStyle = '#4285F4'
            ctx2.fill()
            let cLabel = pt.cotas >= 1000000 ? (pt.cotas / 1000000).toFixed(1) + 'M' :
                pt.cotas >= 1000 ? (pt.cotas / 1000).toFixed(1) + 'K' :
                    Math.round(pt.cotas).toLocaleString('pt-BR')
            ctx2.fillText(cLabel, pt._x, Math.max(pt._cy - 10, 10))
        }
    }

    ctx2.textAlign = 'center'
    ctx2.fillStyle = '#888'
    ctx2.font = '10px system-ui, sans-serif'
    let maxLabels = Math.floor(pW / 55)
    let mStep = Math.max(1, Math.floor(cotistas.length / maxLabels))
    for (let i = 0; i < cotistas.length; i += mStep) {
        let x = pad.left + (i + 0.5) * step
        ctx2.fillText(fmtMonthYear(cotistas[i].dateObj), x, h - pad.bottom + 16)
    }
    canvas._cotData = cotistas
    canvas._cotW = w
    canvas._cotH = h
    canvas._cotPad = pad
    canvas._cotStep = step
    canvas._cotLen = cotistas.length

    let overlay2 = document.getElementById('chart-cotistas-overlay')
    if (overlay2) {
        let octx2 = overlay2.getContext('2d')
        let dpr3 = window.devicePixelRatio || 1
        overlay2.style.width = w + 'px'
        overlay2.style.height = h + 'px'
        overlay2.width = w * dpr3
        overlay2.height = h * dpr3
        octx2.setTransform(dpr3, 0, 0, dpr3, 0, 0)
        octx2.clearRect(0, 0, w, h)
    }
}

function drawCotOverlay(cx, cotW, cotH) {
    let overlay2 = document.getElementById('chart-cotistas-overlay')
    if (!overlay2) return
    let octx2 = overlay2.getContext('2d')
    let dpr3 = window.devicePixelRatio || 1
    octx2.setTransform(dpr3, 0, 0, dpr3, 0, 0)
    octx2.clearRect(0, 0, cotW, cotH)
    if (cx < 0) return
    octx2.strokeStyle = 'rgba(255, 255, 255, 0.25)'
    octx2.lineWidth = 1
    octx2.setLineDash([4, 4])
    octx2.beginPath()
    octx2.moveTo(cx, 0)
    octx2.lineTo(cx, cotH)
    octx2.stroke()
    octx2.setLineDash([])
}

function clearOverlay() {
    if (!overlayCtx) overlayCtx = document.getElementById('chart-overlay').getContext('2d')
    overlayCtx.clearRect(0, 0, chartW, chartH)
}

document.addEventListener('DOMContentLoaded', function () {
    canvas = document.getElementById('chart')
    tooltipEl = document.getElementById('tooltip')

    canvas.addEventListener('mousemove', function (e) {
        if (!canvas._chartData || canvas._chartData.length < 2) {
            tooltipEl.classList.remove('visible')
            return
        }
        let data = canvas._chartData
        let xPos = canvas._xPos
        let yPos = canvas._yPos
        let rect = canvas.getBoundingClientRect()
        let mx = e.clientX - rect.left
        let my = e.clientY - rect.top
        let minDist = Infinity
        let nearest = -1
        for (let i = 0; i < data.length; i++) {
            let dist = Math.abs(xPos(i) - mx)
            if (dist < minDist) { minDist = dist; nearest = i }
        }
        let step = chartW / data.length
        if (minDist > Math.max(step * 1.5, 20)) {
            tooltipEl.classList.remove('visible')
            clearOverlay()
            return
        }
        let pt = data[nearest]
        let cx = xPos(nearest)
        let cy = yPos(pt.fechamento)

        // Check if hovering near a marker icon (top area)
        let markerEl = document.getElementById('tt-marker')
        let markerSub = document.getElementById('tt-marker-sub')
        let markerInfo = canvas._markerData
        let foundMarker = null
        if (markerInfo && my < 30) {
            for (let m of markerInfo) {
                if (Math.abs(m.x - mx) < 10) {
                    foundMarker = m
                    break
                }
            }
        }
        if (foundMarker) {
            if (foundMarker.tipo === 'youtube') {
                markerEl.textContent = 'Video'
                markerSub.textContent = foundMarker.subtipo || ''
            } else {
                let label = foundMarker.tipo === 'relatorio' ? 'Relatorio' : foundMarker.tipo === 'relevante' ? 'Fato Relevante' : 'Dividendo'
                markerEl.textContent = label
                markerSub.textContent = foundMarker.subtipo || ''
            }
            markerEl.style.display = ''
            markerSub.style.display = ''
        } else {
            markerEl.style.display = 'none'
            markerSub.style.display = 'none'
        }

        document.getElementById('tt-date').textContent = fmtDateBR(pt.dateObj)
        document.getElementById('tt-price').textContent = fmtBRL(pt.fechamento)
        let volEl = document.getElementById('tt-vol')
        volEl.textContent = (pt.volume != null && pt.volume > 0) ? 'Vol: ' + pt.volume.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }) : ''
        tooltipEl.style.left = Math.min(cx + 16, chartW - 180) + 'px'
        tooltipEl.style.top = Math.max(cy - 30, 10) + 'px'
        tooltipEl.classList.add('visible')
        drawOverlay(cx, cy)
    })

    canvas.addEventListener('mouseleave', () => { tooltipEl.classList.remove('visible'); clearOverlay() })

    canvas.addEventListener('click', function (e) {
        if (!canvas._markerData) return
        let rect = canvas.getBoundingClientRect()
        let mx = e.clientX - rect.left
        for (let m of canvas._markerData) {
            if (Math.abs(m.x - mx) < 8 && (e.clientY - rect.top) < 30) {
                window.open(m.link, '_blank')
                return
            }
        }
    })

    document.querySelectorAll('.btn-range').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.btn-range').forEach(b => b.classList.remove('active'))
            this.classList.add('active')
            updateView(parseInt(this.dataset.range))
        })
    })

    let params = new URLSearchParams(location.search)
    let ticker = params.get('ticker') || ''
    if (ticker) document.getElementById('fund-search').value = ticker.toUpperCase()

    loadFundList().then(() => {
        let t = ticker || (fundosDisponiveis.length > 0 ? fundosDisponiveis[0] : '')
        if (t) { currentTicker = t.toUpperCase(); loadFund(currentTicker) }
    })
})
"""Build HTML mockups of the Email Scraper screen in four visual styles."""
from pathlib import Path

OUT = Path(__file__).parent
TOOLS = ["Website Finder", "Link Collector", "Email Scraper", "Link Extractor", "Duplicate Remover",
         "Keyword Filter", "Text Stripper"]
SITES = ["acme-defence.com", "firma.com.tr", "bird-aero.example", "excalibur.cz", "parked-domain.net",
         "guarded.example", "old-site.example", "regula.example", "hobbywing.example"]
EMAILS = [("info@acme-defence.com", "acme-defence.com", "Site data"),
          ("sales@acme-defence.com", "acme-defence.com", "mailto link"),
          ("bilgi@firma.com.tr", "firma.com.tr", "Page text"),
          ("contact@bird-aero.example", "bird-aero.example", "mailto link"),
          ("office@excalibur.cz", "excalibur.cz", "Cloudflare"),
          ("export@excalibur.cz", "excalibur.cz", "Page text"),
          ("support@regula.example", "regula.example", "mailto link")]
ROWS = [("acme-defence.com", "FOUND", 2, "1.2s"), ("firma.com.tr", "FOUND", 1, "0.9s"),
        ("bird-aero.example", "FOUND", 1, "2.4s"), ("excalibur.cz", "FOUND", 2, "1.6s"),
        ("parked-domain.net", "PARKED", 0, "0.6s"), ("guarded.example", "BLOCKED", 0, "19.3s"),
        ("old-site.example", "FAILED", 0, "0.4s")]
FONTS = ("https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Orbitron:wght@500;700;900"
         "&family=Rajdhani:wght@500;600;700&family=Share+Tech+Mono&family=Space+Grotesk:wght@400;500;600;700"
         "&family=Inter:wght@400;500;600&display=swap")


def page(css: str, body: str) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{FONTS}">'
            f"<style>*{{box-sizing:border-box;margin:0;padding:0}}html,body{{width:1280px;height:800px;overflow:hidden}}"
            f"{css}</style></head><body>{body}</body></html>")


# ---------------------------------------------------------------- A: terminal
def terminal() -> str:
    css = """
    body{background:#030703;color:#9cf59a;font:13px 'JetBrains Mono',monospace;display:flex}
    body::after{content:"";position:fixed;inset:0;pointer-events:none;
      background:repeating-linear-gradient(0deg,rgba(0,0,0,.22) 0 1px,transparent 1px 3px)}
    .side{width:220px;border-right:1px solid #134d13;padding:18px 0;display:flex;flex-direction:column}
    .logo{color:#39ff14;font-weight:700;padding:0 18px 4px;font-size:15px;text-shadow:0 0 8px #39ff1499}
    .logo small{display:block;color:#2f8a2f;font-weight:400;font-size:11px;margin-top:2px}
    .nav{margin-top:22px}.nav div{padding:7px 18px;color:#4fa84d}
    .nav div.on{color:#030703;background:#39ff14;font-weight:700}
    .nav .sep{color:#1f5f1f;padding:12px 18px 4px;font-size:11px}
    .main{flex:1;padding:20px 26px;display:flex;flex-direction:column;gap:14px}
    .prompt{color:#39ff14;font-size:18px;font-weight:700;text-shadow:0 0 10px #39ff1466}
    .prompt span{color:#2f8a2f;font-weight:400}.cur{display:inline-block;width:10px;height:18px;background:#39ff14;vertical-align:-3px;margin-left:4px}
    .desc{color:#3d8f3c;font-size:12px;margin-top:-8px}
    .bar{border:1px solid #134d13;padding:9px 12px;display:flex;gap:18px;align-items:center;color:#62c560}
    .bar .seg span{padding:4px 10px;border:1px solid #1f6f1f;color:#4fa84d}.bar .seg span.on{background:#39ff14;color:#030703;border-color:#39ff14;font-weight:700}
    .bar .push{margin-left:auto}.chk{color:#39ff14}
    .grid{flex:1;display:grid;grid-template-columns:360px 1fr;gap:14px;min-height:0}
    .box{border:1px solid #1d6b1d;position:relative;padding:22px 14px 14px;display:flex;flex-direction:column;min-height:0}
    .box>.t{position:absolute;top:-9px;left:12px;background:#030703;padding:0 6px;color:#39ff14;font-weight:700}
    .box>.t i{color:#2f8a2f;font-style:normal;font-weight:400}
    .ed{flex:1;color:#9cf59a;line-height:1.75;overflow:hidden}.ed b{color:#2f8a2f;font-weight:400;margin-right:10px}
    .btn{border:1px solid #39ff14;color:#39ff14;padding:8px 14px;text-align:center;font-weight:700}
    .btn.p{background:#39ff14;color:#030703;box-shadow:0 0 14px #39ff1455}
    .row{display:flex;gap:8px;margin-top:10px}.row .btn{flex:1}.row .btn.s{flex:0 0 90px;border-color:#1f6f1f;color:#2f8a2f}
    .prog{margin-top:10px;color:#62c560;font-size:12px}.prog .b{color:#39ff14}
    .stats{color:#62c560;margin-bottom:10px}.stats b{color:#39ff14}.stats .w{color:#ffb000}.stats .r{color:#ff4b4b}
    .tabs{display:flex;gap:4px;margin-bottom:8px}.tabs span{padding:4px 10px;color:#2f8a2f}.tabs span.on{color:#39ff14;border-bottom:2px solid #39ff14}
    table{width:100%;border-collapse:collapse;font-size:12px}td{padding:5px 6px;border-bottom:1px dashed #0f3a0f}
    th{text-align:left;color:#2f8a2f;font-weight:400;padding:5px 6px;border-bottom:1px solid #1d6b1d}
    .ok{color:#39ff14}.wa{color:#ffb000}.er{color:#ff4b4b}.mu{color:#2f8a2f}
    .foot{display:flex;gap:8px;margin-top:auto;padding-top:10px}.foot .btn{font-weight:500;padding:6px 10px}
    .head{display:flex;align-items:center}.head .btn{margin-left:auto}
    """
    nav = "".join(f'<div class="{"on" if t == "Email Scraper" else ""}">{"&gt; " if t == "Email Scraper" else "  "}'
                  f'{t.lower().replace(" ", "_")}</div>' for t in TOOLS)
    sites = "".join(f"<div><b>{i:02d}</b>{s}</div>" for i, s in enumerate(SITES, 1))
    tag = {"FOUND": "ok", "PARKED": "mu", "BLOCKED": "wa", "FAILED": "er"}
    rows = "".join(f'<tr><td>{s}</td><td class="{tag[st]}">[{st}]</td><td>{n}</td><td class="mu">{t}</td></tr>'
                   for s, st, n, t in ROWS)
    body = f"""
    <div class="side"><div class="logo">SIEVE_<small>v0.13 // by wiesdante</small></div>
      <div class="nav"><div class="sep"># main</div><div>  home</div><div class="sep"># scraping</div>{nav}
      <div class="sep"># system</div><div>  settings</div><div>  about</div></div></div>
    <div class="main">
      <div><div class="prompt"><span>root@sieve:~$</span> email_scraper<span class="cur"></span></div></div>
      <div class="desc">// finds contact addresses on a list of websites, with junk filtering</div>
      <div class="bar"><span class="seg"><span class="on">STANDARD</span><span>DIRECT</span></span>
        <span><span class="chk">[x]</span> filter_junk</span><span class="btn" style="padding:3px 10px">rules</span>
        <span><span class="mu">[ ]</span> proxies</span><span class="push">browser=<b class="ok">smart</b></span><span>threads=<b class="ok">10</b></span></div>
      <div class="grid">
        <div class="box"><div class="t">TARGETS <i>· 9 sites</i></div><div class="ed">{sites}</div>
          <div class="prog">[<span class="b">████████████░░░░░░</span>] 7/9 · 00:24 · eta 00:07</div>
          <div class="row"><div class="btn p">[ RUN ]</div><div class="btn s">[ STOP ]</div></div></div>
        <div class="box"><div class="t">OUTPUT</div>
          <div class="stats">sites <b>7</b> · emails <b>7</b> · found <b>4</b> · <span class="w">blocked 1</span> · <span class="r">failed 1</span> · parked 1</div>
          <div class="tabs"><span class="on">emails</span><span>details</span><span>sites</span><span>rejected(2)</span><span>log</span></div>
          <table><tr><th>SITE</th><th>STATUS</th><th>EMAILS</th><th>TIME</th></tr>{rows}</table>
          <div class="foot"><div class="btn p">COPY EMAILS</div><div class="btn">copy details</div><div class="btn">send_to ▾</div><div class="btn">retry_failed</div></div></div>
      </div></div>"""
    return page(css, body)


# ----------------------------------------------------------------- B: neon
def neon() -> str:
    css = """
    body{background:radial-gradient(1200px 700px at 80% -10%,#3a0f5c 0,transparent 60%),radial-gradient(900px 600px at -10% 110%,#06305a 0,transparent 55%),#07040f;
      color:#d9d2ff;font:15px 'Rajdhani',sans-serif;display:flex;font-weight:500}
    .side{width:84px;background:#0c0718cc;border-right:1px solid #2a1a4a;display:flex;flex-direction:column;align-items:center;padding:16px 0;gap:10px}
    .mark{width:46px;height:46px;clip-path:polygon(25% 0,100% 0,100% 75%,75% 100%,0 100%,0 25%);background:linear-gradient(135deg,#ff2bd6,#7a3cff);display:grid;place-items:center;font:900 18px Orbitron;color:#fff;margin-bottom:14px}
    .ic{width:46px;height:40px;display:grid;place-items:center;color:#6f63a8;font:700 12px Orbitron;border:1px solid transparent}
    .ic.on{color:#fff;border-color:#00f0ff;box-shadow:0 0 12px #00f0ff88,inset 0 0 10px #00f0ff44;background:#00f0ff14}
    .main{flex:1;padding:22px 26px;display:flex;flex-direction:column;gap:14px}
    h1{font:900 26px Orbitron;letter-spacing:3px;color:#fff;text-shadow:0 0 18px #ff2bd6aa}
    h1 span{color:#00f0ff;text-shadow:0 0 14px #00f0ffaa}.sub{color:#8e83c9;margin-top:-6px;letter-spacing:1px}
    .cut{clip-path:polygon(14px 0,100% 0,100% calc(100% - 14px),calc(100% - 14px) 100%,0 100%,0 14px)}
    .bar{background:linear-gradient(90deg,#1a0f33,#120a26);border:1px solid #3a2766;padding:10px 16px;display:flex;gap:16px;align-items:center}
    .seg{display:flex}.seg span{padding:6px 16px;font:700 12px Orbitron;letter-spacing:1px;color:#8e83c9;border:1px solid #3a2766}
    .seg span.on{background:linear-gradient(90deg,#ff2bd6,#a43cff);color:#fff;border-color:#ff2bd6;box-shadow:0 0 14px #ff2bd677}
    .tog{display:flex;align-items:center;gap:8px}.sw{width:34px;height:16px;border-radius:8px;background:#2a1a4a;position:relative}
    .sw.on{background:#00f0ff55;box-shadow:0 0 8px #00f0ff88}.sw::after{content:"";position:absolute;top:2px;left:2px;width:12px;height:12px;border-radius:6px;background:#8e83c9}
    .sw.on::after{left:20px;background:#00f0ff}
    .chip{border:1px solid #3a2766;padding:5px 12px;font:600 12px Orbitron;letter-spacing:1px;color:#c9c0ff}.push{margin-left:auto}
    .grid{flex:1;display:grid;grid-template-columns:350px 1fr;gap:16px;min-height:0}
    .panel{background:linear-gradient(180deg,#160d2bee,#0e0820ee);border:1px solid #33215c;padding:16px;display:flex;flex-direction:column;min-height:0;position:relative}
    .panel::before{content:"";position:absolute;left:0;top:0;width:70px;height:2px;background:#00f0ff;box-shadow:0 0 10px #00f0ff}
    .pt{font:700 14px Orbitron;letter-spacing:2px;color:#fff;margin-bottom:12px}.pt i{font:500 13px Rajdhani;color:#8e83c9;font-style:normal;letter-spacing:0}
    .ed{flex:1;background:#07040fcc;border:1px solid #2a1a4a;padding:10px 12px;font:13px 'JetBrains Mono';color:#bfb6ff;line-height:1.8}
    .btn{padding:10px 16px;font:700 13px Orbitron;letter-spacing:2px;text-align:center;color:#d9d2ff;border:1px solid #4a3480;background:#1a0f33}
    .btn.p{background:linear-gradient(90deg,#ff2bd6,#7a3cff);border:none;color:#fff;box-shadow:0 0 18px #ff2bd666}
    .row{display:flex;gap:10px;margin-top:12px}.row .p{flex:1}
    .prog{height:6px;background:#2a1a4a;margin-top:12px}.prog div{height:100%;width:78%;background:linear-gradient(90deg,#00f0ff,#ff2bd6);box-shadow:0 0 10px #00f0ff}
    .pl{font-size:13px;color:#8e83c9;margin-top:6px}
    .stats{display:flex;gap:10px;margin-bottom:12px}.st{flex:1;border:1px solid #2a1a4a;padding:8px 10px;background:#0b0618}
    .st b{display:block;font:700 22px Orbitron;color:#fff}.st span{font-size:12px;color:#8e83c9;letter-spacing:1px;text-transform:uppercase}
    .st.c b{color:#00f0ff;text-shadow:0 0 10px #00f0ff88}.st.m b{color:#ff2bd6;text-shadow:0 0 10px #ff2bd688}.st.y b{color:#ffd23f}
    .tabs{display:flex;gap:20px;border-bottom:1px solid #2a1a4a;margin-bottom:6px}.tabs span{padding:6px 0;color:#8e83c9;font-weight:600;letter-spacing:1px}
    .tabs span.on{color:#00f0ff;border-bottom:2px solid #00f0ff;text-shadow:0 0 8px #00f0ff}
    table{width:100%;border-collapse:collapse;font-size:15px}td{padding:6px 4px;border-bottom:1px solid #1d1338}
    .e{font:13px 'JetBrains Mono';color:#e6e0ff}.mu{color:#8e83c9}.h{color:#6f63a8;font-size:13px}
    .foot{display:flex;gap:10px;margin-top:auto;padding-top:12px}.foot .btn{padding:7px 12px;font-size:11px}
    """
    icons = "".join(f'<div class="ic{" on" if t == "Email Scraper" else ""}">{t.split()[0][:2].upper()}</div>' for t in TOOLS)
    sites = "<br>".join(SITES)
    rows = "".join(f'<tr><td class="e">{e}</td><td class="mu">{s}</td><td class="h">{h}</td></tr>' for e, s, h in EMAILS)
    body = f"""
    <div class="side"><div class="mark">S</div><div class="ic">HO</div>{icons}<div style="flex:1"></div><div class="ic">ST</div></div>
    <div class="main"><div><h1>EMAIL <span>SCRAPER</span></h1></div><div class="sub">Finds contact addresses on a list of websites</div>
      <div class="bar cut"><div class="seg"><span class="on">STANDARD</span><span>DIRECT</span></div>
        <div class="tog"><div class="sw on"></div>Filter junk</div><div class="chip">RULES</div>
        <div class="tog"><div class="sw"></div>Proxies</div><div class="chip push">BROWSER · SMART</div><div class="chip">10 THREADS</div></div>
      <div class="grid">
        <div class="panel cut"><div class="pt">TARGETS <i>· 9 sites</i></div><div class="ed">{sites}</div>
          <div class="prog"><div></div></div><div class="pl">7 / 9 sites · 0:24 · about 0:07 left</div>
          <div class="row"><div class="btn p">START</div><div class="btn">STOP</div></div></div>
        <div class="panel cut"><div class="pt">RESULTS</div>
          <div class="stats"><div class="st c"><b>7</b><span>emails</span></div><div class="st"><b>4</b><span>found</span></div>
            <div class="st y"><b>1</b><span>blocked</span></div><div class="st m"><b>1</b><span>failed</span></div></div>
          <div class="tabs"><span class="on">EMAILS</span><span>DETAILS</span><span>SITES</span><span>REJECTED</span><span>LOG</span></div>
          <table>{rows}</table>
          <div class="foot"><div class="btn p">COPY EMAILS</div><div class="btn">DETAILS</div><div class="btn">SEND TO ▾</div><div class="btn">RETRY FAILED</div></div></div>
      </div></div>"""
    return page(css, body)


# ------------------------------------------------------------------ C: HUD
def hud() -> str:
    css = """
    body{background:#0a0c0d;color:#c9d1d3;font:15px 'Rajdhani',sans-serif;font-weight:500;display:flex;
      background-image:linear-gradient(#ffffff06 1px,transparent 1px),linear-gradient(90deg,#ffffff06 1px,transparent 1px);background-size:32px 32px}
    .side{width:236px;background:#0d1011;border-right:1px solid #262c2e;padding:18px 14px;display:flex;flex-direction:column}
    .brand{font:700 20px 'Share Tech Mono';letter-spacing:6px;color:#ffb000}.brand small{display:block;font:12px 'Share Tech Mono';letter-spacing:2px;color:#5c6669;margin-top:4px}
    .grp{font:12px 'Share Tech Mono';color:#5c6669;letter-spacing:2px;margin:22px 0 6px}
    .it{display:flex;gap:10px;padding:7px 10px;color:#93a0a3;letter-spacing:1px;text-transform:uppercase;font-weight:600;font-size:14px}
    .it em{font:12px 'Share Tech Mono';color:#3e4649;font-style:normal;width:20px}
    .it.on{color:#0a0c0d;background:#ffb000}.it.on em{color:#0a0c0d}
    .main{flex:1;padding:20px 26px;display:flex;flex-direction:column;gap:14px}
    .top{display:flex;align-items:flex-end;gap:16px}.code{font:12px 'Share Tech Mono';color:#ffb000;letter-spacing:2px}
    h1{font:700 30px 'Rajdhani';letter-spacing:4px;text-transform:uppercase;color:#eef3f4;line-height:1}
    .top .sys{margin-left:auto;font:12px 'Share Tech Mono';color:#5c6669;text-align:right;letter-spacing:1px}.sys b{color:#3fd0a0;font-weight:400}
    .bk{position:relative;border:1px solid #1e2426;background:#0d1011e6}
    .bk::before,.bk::after{content:"";position:absolute;width:14px;height:14px;border:2px solid #ffb000}
    .bk::before{top:-2px;left:-2px;border-right:none;border-bottom:none}.bk::after{bottom:-2px;right:-2px;border-left:none;border-top:none}
    .bar{padding:10px 14px;display:flex;gap:18px;align-items:center;text-transform:uppercase;letter-spacing:1px;font-weight:600;font-size:14px}
    .seg span{padding:5px 14px;border:1px solid #2f3739;color:#93a0a3}.seg span.on{background:#ffb00022;border-color:#ffb000;color:#ffb000}
    .led{display:inline-block;width:8px;height:8px;background:#3fd0a0;margin-right:7px;box-shadow:0 0 8px #3fd0a0}.led.off{background:#3e4649;box-shadow:none}
    .val{font:13px 'Share Tech Mono';color:#ffb000}.push{margin-left:auto}
    .grid{flex:1;display:grid;grid-template-columns:350px 1fr;gap:16px;min-height:0}
    .panel{padding:14px;display:flex;flex-direction:column;min-height:0}
    .pt{display:flex;align-items:center;gap:10px;font:700 15px Rajdhani;letter-spacing:3px;text-transform:uppercase;color:#eef3f4;margin-bottom:12px}
    .pt em{font:12px 'Share Tech Mono';color:#ffb000;font-style:normal;letter-spacing:1px}.pt i{margin-left:auto;font:12px 'Share Tech Mono';color:#5c6669;font-style:normal}
    .ed{flex:1;font:13px 'JetBrains Mono';color:#c9d1d3;line-height:1.8;border-left:2px solid #262c2e;padding-left:12px}.ed b{color:#3e4649;font-weight:400;margin-right:10px}
    .btn{padding:9px 14px;text-align:center;text-transform:uppercase;letter-spacing:2px;font-weight:700;font-size:14px;border:1px solid #3a4244;color:#c9d1d3}
    .btn.p{background:#ffb000;color:#0a0c0d;border-color:#ffb000}
    .row{display:flex;gap:10px;margin-top:12px}.row .p{flex:1}
    .ticks{display:flex;gap:3px;margin-top:12px}.ticks i{flex:1;height:10px;background:#ffb000}.ticks i.o{background:#262c2e}
    .pl{font:12px 'Share Tech Mono';color:#5c6669;margin-top:6px;letter-spacing:1px}
    .read{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:#1e2426;margin-bottom:12px}
    .read div{background:#0d1011;padding:8px 10px}.read b{display:block;font:30px 'Share Tech Mono';color:#eef3f4;line-height:1}
    .read span{font:11px 'Share Tech Mono';color:#5c6669;letter-spacing:2px}.read .g b{color:#3fd0a0}.read .a b{color:#ffb000}.read .r b{color:#ff5a4f}
    .tabs{display:flex;gap:2px;margin-bottom:6px}.tabs span{padding:5px 12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;font-size:13px;color:#5c6669;border-bottom:2px solid #1e2426}
    .tabs span.on{color:#ffb000;border-color:#ffb000}
    table{width:100%;border-collapse:collapse}td{padding:6px 6px;border-bottom:1px solid #161b1c;font-size:14px}
    th{font:11px 'Share Tech Mono';letter-spacing:2px;color:#5c6669;text-align:left;padding:4px 6px;font-weight:400}
    .m{font:13px 'JetBrains Mono'}.s{font:12px 'Share Tech Mono';letter-spacing:1px}.g{color:#3fd0a0}.a{color:#ffb000}.r{color:#ff5a4f}.d{color:#5c6669}
    .foot{display:flex;gap:8px;margin-top:auto;padding-top:12px}.foot .btn{padding:6px 12px;font-size:12px}
    """
    items = "".join(f'<div class="it{" on" if t == "Email Scraper" else ""}"><em>{i:02d}</em>{t}</div>' for i, t in enumerate(TOOLS, 1))
    sites = "".join(f"<div><b>{i:02d}</b>{s}</div>" for i, s in enumerate(SITES, 1))
    tag = {"FOUND": "g", "PARKED": "d", "BLOCKED": "a", "FAILED": "r"}
    rows = "".join(f'<tr><td class="m">{s}</td><td class="s {tag[st]}">■ {st}</td><td class="s">{n}</td><td class="s d">{t}</td></tr>'
                   for s, st, n, t in ROWS)
    ticks = "".join('<i></i>' if i < 14 else '<i class="o"></i>' for i in range(18))
    body = f"""
    <div class="side"><div class="brand">SIEVE<small>DATA OPS // WIESDANTE</small></div>
      <div class="grp">— SCRAPING</div>{items}<div style="flex:1"></div><div class="grp">— SYSTEM</div>
      <div class="it"><em>S1</em>Settings</div><div class="it"><em>S2</em>About</div></div>
    <div class="main"><div class="top"><div><div class="code">MODULE 03 // CONTACT EXTRACTION</div><h1>Email Scraper</h1></div>
        <div class="sys">SESSION ACTIVE · <b>ONLINE</b><br>UTC+3 07:42:19</div></div>
      <div class="bar bk"><div class="seg"><span class="on">Standard</span><span>Direct</span></div>
        <span><i class="led"></i>Filter junk</span><div class="btn" style="padding:3px 12px;font-size:12px">Rules</div>
        <span><i class="led off"></i>Proxies</span><span class="push">Browser <span class="val">SMART</span></span><span>Threads <span class="val">10</span></span></div>
      <div class="grid">
        <div class="panel bk"><div class="pt"><em>01</em>Targets<i>09 SITES</i></div><div class="ed">{sites}</div>
          <div class="ticks">{ticks}</div><div class="pl">PROGRESS 07/09 · T+00:24 · ETA 00:07</div>
          <div class="row"><div class="btn p">Start</div><div class="btn">Stop</div></div></div>
        <div class="panel bk"><div class="pt"><em>02</em>Results</div>
          <div class="read"><div><b>07</b><span>SITES</span></div><div class="g"><b>07</b><span>EMAILS</span></div><div class="g"><b>04</b><span>FOUND</span></div>
            <div class="a"><b>01</b><span>BLOCKED</span></div><div class="r"><b>01</b><span>FAILED</span></div></div>
          <div class="tabs"><span>Emails</span><span>Details</span><span class="on">Sites</span><span>Rejected</span><span>Log</span></div>
          <table><tr><th>SITE</th><th>STATUS</th><th>EMAILS</th><th>TIME</th></tr>{rows}</table>
          <div class="foot"><div class="btn p">Copy emails</div><div class="btn">Copy details</div><div class="btn">Send to ▾</div><div class="btn">Retry failed</div></div></div>
      </div></div>"""
    return page(css, body)


# --------------------------------------------------------------- D: midnight
def midnight() -> str:
    css = """
    body{background:radial-gradient(900px 500px at 70% -20%,#2b1d6b55,transparent 70%),radial-gradient(700px 500px at 0% 120%,#0e3a6b44,transparent 70%),#08090d;
      color:#e7e9f2;font:14px 'Inter',sans-serif;display:flex}
    .side{width:232px;padding:20px 14px;display:flex;flex-direction:column;gap:4px;border-right:1px solid #ffffff0d;background:#ffffff03}
    .brand{display:flex;align-items:center;gap:10px;font:700 18px 'Space Grotesk';margin-bottom:22px;padding:0 6px}
    .lg{width:30px;height:30px;border-radius:9px;background:conic-gradient(from 200deg,#7c5cff,#3fb6ff,#c86bff,#7c5cff);box-shadow:0 0 20px #7c5cff66}
    .brand small{display:block;font:500 11px Inter;color:#6b7085}
    .gl{font:600 11px Inter;color:#565b70;letter-spacing:1.4px;margin:14px 8px 6px}
    .it{padding:8px 10px;border-radius:9px;color:#a4a8bb;display:flex;gap:10px;align-items:center}.it i{width:16px;height:16px;border-radius:5px;border:1.5px solid #565b70}
    .it.on{background:linear-gradient(90deg,#7c5cff33,#7c5cff0a);color:#fff;box-shadow:inset 0 0 0 1px #7c5cff55}.it.on i{border-color:#9d86ff}
    .main{flex:1;padding:24px 28px;display:flex;flex-direction:column;gap:16px}
    h1{font:700 28px 'Space Grotesk';letter-spacing:-.5px}h1 span{background:linear-gradient(90deg,#9d86ff,#3fb6ff);-webkit-background-clip:text;color:transparent}
    .sub{color:#7d8197;margin-top:-10px}
    .glass{background:linear-gradient(180deg,#ffffff0b,#ffffff05);border:1px solid #ffffff12;border-radius:16px;box-shadow:0 10px 40px #0007}
    .bar{padding:10px 14px;display:flex;gap:14px;align-items:center}
    .seg{display:flex;background:#00000040;border-radius:10px;padding:3px}.seg span{padding:6px 14px;border-radius:8px;color:#a4a8bb;font-weight:500}
    .seg span.on{background:linear-gradient(90deg,#7c5cff,#5b7cff);color:#fff;box-shadow:0 4px 14px #7c5cff55}
    .pill{padding:6px 12px;border-radius:9px;background:#ffffff0a;border:1px solid #ffffff12;color:#c8cbd9}.pill b{color:#fff;font-weight:600}
    .tg{display:flex;gap:8px;align-items:center;color:#c8cbd9}.sw{width:30px;height:18px;border-radius:9px;background:#ffffff1a;position:relative}
    .sw.on{background:linear-gradient(90deg,#7c5cff,#3fb6ff)}.sw::after{content:"";position:absolute;top:3px;left:3px;width:12px;height:12px;border-radius:6px;background:#fff}.sw.on::after{left:15px}
    .push{margin-left:auto}
    .grid{flex:1;display:grid;grid-template-columns:350px 1fr;gap:16px;min-height:0}
    .panel{padding:18px;display:flex;flex-direction:column;min-height:0}
    .pt{font:600 16px 'Space Grotesk';margin-bottom:12px;display:flex;align-items:center;gap:8px}.pt i{font:400 13px Inter;color:#6b7085;font-style:normal}
    .ed{flex:1;background:#00000035;border:1px solid #ffffff0d;border-radius:12px;padding:12px 14px;font:13px 'JetBrains Mono';color:#c8cbd9;line-height:1.8}
    .btn{padding:10px 16px;border-radius:11px;text-align:center;font-weight:600;background:#ffffff0d;border:1px solid #ffffff14;color:#dfe1ec}
    .btn.p{background:linear-gradient(90deg,#7c5cff,#4f86ff);border:none;color:#fff;box-shadow:0 8px 24px #6a5cff55}
    .row{display:flex;gap:10px;margin-top:12px}.row .p{flex:1}
    .prog{height:6px;border-radius:3px;background:#ffffff12;margin-top:14px;overflow:hidden}.prog div{height:100%;width:78%;background:linear-gradient(90deg,#7c5cff,#3fb6ff)}
    .pl{font-size:12px;color:#7d8197;margin-top:6px}
    .cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.cd{background:#ffffff08;border:1px solid #ffffff0f;border-radius:12px;padding:10px 12px}
    .cd b{display:block;font:700 22px 'Space Grotesk'}.cd span{font-size:12px;color:#7d8197}.cd.g b{color:#4ade80}.cd.y b{color:#fbbf24}.cd.r b{color:#f87171}
    .tabs{display:flex;gap:6px;margin-bottom:8px}.tabs span{padding:6px 12px;border-radius:8px;color:#8d91a6;font-weight:500}.tabs span.on{background:#ffffff10;color:#fff}
    table{width:100%;border-collapse:collapse}td{padding:7px 6px;border-bottom:1px solid #ffffff09}
    .e{font:13px 'JetBrains Mono'}.mu{color:#7d8197}.tag{font-size:12px;padding:2px 8px;border-radius:6px;background:#7c5cff22;color:#b9a9ff}
    .foot{display:flex;gap:8px;margin-top:auto;padding-top:12px}.foot .btn{padding:7px 12px;font-size:13px}
    """
    items = "".join(f'<div class="it{" on" if t == "Email Scraper" else ""}"><i></i>{t}</div>' for t in TOOLS)
    rows = "".join(f'<tr><td class="e">{e}</td><td class="mu">{s}</td><td><span class="tag">{h}</span></td></tr>' for e, s, h in EMAILS)
    body = f"""
    <div class="side"><div class="brand"><div class="lg"></div><div>Sieve<small>by wiesdante</small></div></div>
      <div class="it"><i></i>Home</div><div class="gl">SCRAPING</div>{items}<div style="flex:1"></div><div class="it"><i></i>Settings</div><div class="it"><i></i>About</div></div>
    <div class="main"><div><h1>Email <span>Scraper</span></h1></div><div class="sub">Finds contact addresses on a list of websites, with junk filtering.</div>
      <div class="bar glass"><div class="seg"><span class="on">Standard</span><span>Direct</span></div>
        <div class="tg"><div class="sw on"></div>Filter junk</div><div class="pill">Rules…</div><div class="tg"><div class="sw"></div>Proxies</div>
        <div class="pill push">Browser: <b>Smart</b></div><div class="pill"><b>10</b> at a time</div></div>
      <div class="grid">
        <div class="panel glass"><div class="pt">Websites <i>· 9 sites</i></div><div class="ed">{"<br>".join(SITES)}</div>
          <div class="prog"><div></div></div><div class="pl">7 / 9 sites · 0:24 · about 0:07 left</div>
          <div class="row"><div class="btn p">Start</div><div class="btn">Stop</div></div></div>
        <div class="panel glass"><div class="pt">Results</div>
          <div class="cards"><div class="cd"><b>7</b><span>Emails</span></div><div class="cd g"><b>4</b><span>Found</span></div>
            <div class="cd y"><b>1</b><span>Blocked</span></div><div class="cd r"><b>1</b><span>Failed</span></div></div>
          <div class="tabs"><span class="on">Emails</span><span>Email details</span><span>Sites</span><span>Rejected (2)</span><span>Log</span></div>
          <table>{rows}</table>
          <div class="foot"><div class="btn p">Copy emails</div><div class="btn">Copy details</div><div class="btn">Send to ▾</div><div class="btn">Retry failed</div></div></div>
      </div></div>"""
    return page(css, body)


if __name__ == "__main__":
    for name, build in (("a-terminal", terminal), ("b-neon", neon), ("c-hud", hud), ("d-midnight", midnight)):
        (OUT / f"{name}.html").write_text(build(), encoding="utf-8")

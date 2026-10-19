"""從 gate-probe 的官方簡報產生測試用固定文字（逐頁 pdftotext 結果＋一覽表原始回應）。"""
import glob, json, os, shutil, sys
sys.path.insert(0, 'gate_pipeline/ops'); sys.path.insert(0, 'gate_pipeline')
import slide_guidance as sg
ROOT = os.environ.get('RESULTS', 'results')
OUT = os.environ.get('FIXTURES', 'gate_pipeline/contract/mops_real/slides')
for co in sys.argv[1:]:
    od = os.path.join(OUT, co); shutil.rmtree(od, ignore_errors=True); os.makedirs(od)
    decks = sg.collect_decks(co, os.path.join(ROOT, co, 'conference'))
    listings = []
    for probe in sorted(glob.glob(os.path.join(ROOT, co, 'conference', '*', 'probe.json'))):
        run = os.path.basename(os.path.dirname(probe)); rep = json.load(open(probe, encoding='utf-8'))
        for q in rep['queries']:
            if q.get('saved_as') and q.get('label') == 'step1_co':
                dst = f"listing_{run}_{q['roc_year']}.bin"
                shutil.copy(os.path.join(os.path.dirname(probe), q['saved_as']), os.path.join(od, dst)); listings.append(dst)
    meta = []
    for d in decks:
        pages = sg.pdf_pages(d['path'])
        json.dump({'names': d['names'], 'sha256': d['sha256'], 'pages': pages}, open(os.path.join(od, d['names'][0] + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        meta.append({'names': d['names'], 'sha256': d['sha256']})
    json.dump({'co_id': co, 'tool': sg.pdftotext_version(), 'listings': listings, 'decks': meta}, open(os.path.join(od, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(co, len(decks), 'decks', len(listings), 'listings', sum(os.path.getsize(os.path.join(od, f)) for f in os.listdir(od)) // 1024, 'KB')

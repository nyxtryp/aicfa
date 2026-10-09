from pathlib import Path


def test_manual_scan_ui_persists_result_and_does_not_reuse_stale_journal_geometry():
    app = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

    assert "manualItems:[],manualView:null" in app
    assert "function allHistory(){return [...ui.manualItems" in app
    assert "if(ui.manualView){" in app
    assert 'x.suppressMarketVisual?null:marketVisual(x.asset,x.mode)' in app
    assert 'visual:data.market_visual||{zones:[],events:[],liquidity:[]}' in app
    assert 'const fresh=await getJson("/journal/scans?limit=50"' not in app

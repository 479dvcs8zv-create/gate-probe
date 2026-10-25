# Gemini 第二意見：固定 JSON 欄位（2026-10-25）

題目原文在擁有者雲端硬碟「Gemini 工作（Claude 交辦）」資料夾：「Gemini 第二意見任務｜群聯 8299｜24 步審查」。換股票時只改代號。
規則：每個數字附來源、日期、網址；查不到寫「缺」；不寫分批價位與停損；不用固定本益比門檻；threeQuestions 只能是「過」「不過」「資料不足」。

```json
{
 "symbol": "8299", "asOf": "YYYY-MM-DD",
 "price": {"close": null, "date": null},
 "ma": {"ma5": null, "ma10": null, "ma20": null, "ma60": null, "ma240": null, "ma60Rising": null, "daysBelowMa60": null, "rsi14": null},
 "revenue": {"month": null, "yoyPct": null, "momPct": null, "high12m": null},
 "quarter": {"period": null, "revenue": null, "grossMarginPct": null, "opMarginPct": null, "netMarginPct": null, "eps": null},
 "eps": {"ttm": null, "consensusCurrentYear": null, "consensusAnalysts": null, "consensusSource": null},
 "valuation": {"pe": null, "pe5yMin": null, "pe5yMedian": null, "pe5yMax": null, "forwardPe": null, "dividendYieldPct": null, "pb": null},
 "chips": {"foreign5d": null, "foreign10d": null, "foreign20d": null, "trust5d": null, "trust10d": null, "trust20d": null, "marginBalanceLots": null, "sblShortBalanceLots": null, "sblShort20dHigh": null, "bigHolderPct4w": [], "pledgePct": null, "cbConversionPrice": null},
 "macro": {"light": null, "claims4w": null, "hyOas": null, "sofrMinusIorbBps": null, "t10y2y": null, "realYield10y": null},
 "threeQuestions": {"technical": null, "chips": null, "fundamental": null},
 "verdict": {"sentence": null, "confidence": null, "changeIf": null},
 "sources": [{"item": null, "source": null, "date": null, "url": null}],
 "missing": [{"item": null, "reason": null}]
}
```

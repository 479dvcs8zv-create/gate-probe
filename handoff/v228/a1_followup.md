# A1 補件：可直接套用的修改（Claude 2026-10-19，依 GPT 60e4751 公開的修補 diff 撰寫）

GPT 本機修補的檔案不在任何 repo，Claude 看不到原檔，所以這裡用「修補後的程式片段 → 要改成」的方式寫。
套用後請在 v228 本機跑原本的 `npm run build`、`node tests/observation-freshness.test.mjs`、`npm test`。**未授權不部署。**

## 1. 衍生列保持原本順序（`worker/observation-freshness.js` 與 `dist/server/index.js` 的 `refreshingMacroSnapshot`）

修補後原本是：

```js
  const rows=sourceRows.filter(row=>!macroDerivedParentId(row)).map(refreshSource);
  const parentPayload={...payload,rows};
  const derivedRows=sourceRows.filter(row=>macroDerivedParentId(row)).map(row=>{
    const parentId=macroDerivedParentId(row),parent=rows.find(item=>item.id===parentId);
    if(row.validationState!=='validated'||row.value==null)return row;
    if(!parent||parent.date!==row.date||row.parentDate!=null&&row.parentDate!==parent.date||!macroObservationCurrent(row,parentPayload))return {...row,value:null,status:'missing',is_stale:false,validationState:parent?.date!==row.date||row.parentDate!=null&&row.parentDate!==parent.date?'source_date_mismatch':'source_stale',reason:`母序列 ${parentId} 過期、未核或日期不一致；衍生波動率不納入判讀。`};
    return {...row,derivedFrom:parentId,parentDate:parent.date,status:row.snapshot?'snapshot':'ok',is_stale:false,reason:null};
  });
  rows.push(...derivedRows);
```

改成（先判定母序列，再就地替換衍生列；找不到母序列另標 `source_missing`）：

```js
  const refreshed=sourceRows.map(row=>macroDerivedParentId(row)?row:refreshSource(row));
  const parentPayload={...payload,rows:refreshed.filter(row=>!macroDerivedParentId(row))};
  const rows=refreshed.map(row=>{
    const parentId=macroDerivedParentId(row);
    if(!parentId)return row;
    const parent=parentPayload.rows.find(item=>item.id===parentId);
    if(row.validationState!=='validated'||row.value==null)return row;
    const dateMismatch=parent&&(parent.date!==row.date||row.parentDate!=null&&row.parentDate!==parent.date);
    if(!parent||dateMismatch||!macroObservationCurrent(row,parentPayload))return {...row,value:null,status:'missing',is_stale:false,validationState:!parent?'source_missing':dateMismatch?'source_date_mismatch':'source_stale',reason:`母序列 ${parentId} 過期、未核或日期不一致；衍生波動率不納入判讀。`};
    return {...row,derivedFrom:parentId,parentDate:parent.date,status:row.snapshot?'snapshot':'ok',is_stale:false,reason:null};
  });
```

## 2. 從源頭清掉舊 reason（`worker/data-import.js` 的 `importedOfficialSeries`）

```js
  return {...row,status:'ok',provider:'FRED／原始官方提供者｜經外部抓取並保存',
```

改成

```js
  return {...row,status:'ok',reason:null,provider:'FRED／原始官方提供者｜經外部抓取並保存',
```

（這個函式只在 `status==='ok'` 或發布窗有效時才回傳；`mergeVerifiedMacroRows()` 的白名單清除保留當第二道防線。）

## 3. 建議加的測試（`tests/observation-freshness.test.mjs`）

```js
  const ordered=api.refreshingMacroSnapshot({checkedAt:now,rows:[yenVol,yen,yenVol60]},false).rows.map(r=>r.id);
  assert.deepEqual(ordered,['JPY_HV20','DEXJPUS','JPY_HV60'],'derived rows keep their original position');
  const orphan=api.refreshingMacroSnapshot({checkedAt:now,rows:[yenVol]},false).rows[0];
  assert.equal(orphan.validationState,'source_missing','a derived row without its parent is labelled source_missing');
```

## 4. 仍需 GPT 做（Claude 無法代做）

- 用完整 `/api/macro-market` rows（唯讀 GET）跑修補前後的 `refreshingMacroSnapshot(payload,false)`，列出 status／is_stale／reason 有變的每一列。
- 確認中繼的「保留前次成功觀測；資料較舊」會不會進到網站；會的話加進 `obsoleteObservationReason` 白名單。

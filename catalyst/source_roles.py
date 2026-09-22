"""Display-only roles from recognized layouts and imported record kinds, not filenames."""
def describe(meta, records):
    kind=meta.get('type','')
    kinds={r['kind'] for r in records}
    sheets={s.get('name') for s in meta.get('sheets',[])}
    roles=[]
    if kind=='BOM 마스터':roles.append('bom')
    elif kind=='구매단가등록':roles.append('price')
    elif 'part' in kinds or 'price' in kinds:roles.append('legacy_master')
    if 'receipt' in kinds or kind=='ERP 월 입고현황':roles.append('receipt')
    if 'plan' in kinds or kind=='월계획 등록 자료':roles.append('plan')
    if 'opening' in kinds:roles.append('opening')
    if 'settlement' in kinds:roles.append('settlement')
    if kind=='월마감 기준자료':roles.append('template')
    if '납품 Summary' in sheets:roles.append('umicore')
    if '8월 마감자료' in sheets or kind in ('출하 배부자료','희성촉매 마감자료'):roles.append('heesung')
    if kind=='한국유미코아 마감자료' and 'umicore' not in roles:roles.append('umicore')
    if kind=='보고서 기준자료':label='필수 아님 · PPT'
    elif any(r!='legacy_master' for r in roles):label='필수 자료'
    elif roles:label='기존 마스터 · 대체 예정'
    else:label='역할 확인 필요'
    return {'roles':roles,'requirement_label':label,
            'applied_months':{k:sorted({r['date'][:7] for r in records if r['kind']==k}) for k in kinds},
            'master_effective_from':min((r['date'] for r in records if r['kind'] in ('part','price')),default=None)}

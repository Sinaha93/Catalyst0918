"""Month-specific planning rates. Never used as transaction prices."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from . import store


def save(payload):
    row = {k: str(payload.get(k, '')).strip() for k in ('period', 'part', 'customer', 'price', 'reason')}
    if not re.fullmatch(r'\d{4}-\d{2}', row['period']):
        raise ValueError('대상 월은 YYYY-MM 형식이어야 합니다')
    date.fromisoformat(row['period'] + '-01')
    if not all(row[k] for k in ('part', 'customer', 'reason')):
        raise ValueError('품번·거래처·추정 사유를 입력해주세요')
    try:
        price = Decimal(row['price'])
    except InvalidOperation:
        raise ValueError('예상 단가는 숫자로 입력해주세요')
    if not price.is_finite() or price < 0:
        raise ValueError('예상 단가는 0 이상의 유한한 숫자여야 합니다')
    row['price'] = str(price)
    enabled = payload.get('enabled', True)
    if not isinstance(enabled, bool):
        raise ValueError('사용 여부는 true 또는 false여야 합니다')
    row.update(enabled=int(enabled), updated=store.stamp())
    with store.db() as c:
        old = c.execute('SELECT * FROM price_estimates WHERE period=? AND part=? AND customer=?',
                        (row['period'], row['part'], row['customer'])).fetchone()
        c.execute('INSERT INTO price_estimates VALUES(:period,:part,:customer,:price,:reason,:enabled,:updated) '
                  'ON CONFLICT(period,part,customer) DO UPDATE SET price=excluded.price, reason=excluded.reason, enabled=excluded.enabled, updated=excluded.updated', row)
        store.audit(c, 'price_estimate', {'before': dict(old) if old else None, 'after': row})
    return {'saved': True}

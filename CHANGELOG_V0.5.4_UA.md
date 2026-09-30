# v0.5.4 — EasyWP low-request batch execution

## Чому v0.5.3 все ще міг отримувати 429

EasyWP Anti-DDoS може тимчасово блокувати серію вхідних запитів з одного IP. Навіть після об'єднання preflight у `get-site-snapshot` сам build усе ще виконував кожну WordPress action окремим HTTP request, а post-build verification робив ще один request.

Також знайдено баг у fallback REST клієнті: `_request_json_candidates()` обходив adaptive retry wrapper, тому текст `persisted after 6 attempts` міг бути неточним для fallback маршруту.

## Що змінилось

- Додано `POST /wp-json/thesis-ai/v1/batch/` у Bridge.
- Кожна логічна action все ще проходить Policy Engine на backend.
- Bridge повторно перевіряє WordPress permissions окремо для кожної action.
- Backend групує actions у batch-и (default 8 дій за один HTTP request).
- Фінальний batch одразу повертає post-build site snapshot.
- Окремий verification REST request після build більше не потрібен.
- Repair actions теж виконуються batch-ами.
- Після transport/rate-limit error backend не продовжує слати наступні batch requests.
- Fallback REST тепер реально використовує 429 backoff/retry wrapper.
- Default 429 cooldown зроблено консервативним: 180–300 секунд, бо EasyWP документує block як тимчасовий на кілька хвилин і часто не повертає `Retry-After`.

## Очікувана кількість inbound REST requests на типовий build

Було: десятки запитів (по одному на кожну action + verification/repair inspection).

Стало приблизно:

1. preflight snapshot;
2. 1–3 build batch requests;
3. optional 1 repair batch.

Тобто зазвичай 2–5 запитів замість десятків.

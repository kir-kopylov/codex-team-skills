# Схема Доказательного Реестра Решений

## Граница Доказательства

Контракт состоит из четырёх файлов. Зелёный валидатор доказывает их внутреннюю согласованность. Он не доказывает подлинность внешнего источника, качество предметного review или неизменность истории относительно не переданного внешнего anchor.

## question-index.tsv

```tsv
question_id	question	question_fingerprint
```

- `question_id` — положительное целое без ведущих нулей.
- `question_fingerprint` — SHA-256 от NFC-нормализованного вопроса со схлопнутыми пробелами.
- Fingerprint первого `BASELINE` для ID неизменяем. Новый смысл требует нового ID.

## answer-register.csv

```csv
question_id,status,answer,evidence,depends_on,semantic_review
```

Статусы: `UNASSESSED`, `ANSWERED`, `DERIVED`, `UNKNOWN`, `PENDING_CONTEXT`, `CONFLICT`.

`semantic_review`:

- `ANSWERED`, `DERIVED`: `UNREVIEWED` или `REVIEWED`;
- все открытые статусы: `NOT_REQUIRED`.

Разрешённые ссылки в `evidence`:

```text
[evidence:source-id]
[needed:source-id]
[decision:4;8-10]
```

Все квадратные скобки в этом поле зарезервированы под ссылки. Повреждённая или неизвестная ссылка — ошибка.

Правила статусов:

- `ANSWERED` требует хотя бы один `[evidence:...]` на `OBSERVED` source.
- `DERIVED` требует равные множества `decision` и `depends_on` либо `OBSERVED` source типа `delegation`.
- `UNKNOWN` начинается с `не знаю —`, содержит непустое объяснение и `[needed:...]` на `MISSING` source.
- `PENDING_CONTEXT` начинается с точной метки, объясняет блокировку и имеет равные множества `decision` и `depends_on`.
- `CONFLICT` требует два разных `OBSERVED` evidence source; legacy baseline допускает один только до review.

Диапазон ID разворачивается пересечением с реальным индексом. Валидатор не материализует произвольный числовой диапазон.

## source-manifest.csv

```csv
source_id,source_type,availability,locator,content_hash,observed_at
```

`source_type`: `user_turn`, `file`, `tool_output`, `system_record`, `delegation`, `legacy_text`, `expected_file`, `expected_measurement`.

- `OBSERVED`: обязательны locator, `sha256:<64 hex>` и ISO timestamp с часовым поясом.
- `MISSING`: обязательна ожидаемая locator, но `content_hash` и `observed_at` пусты.
- `MISSING` разрешён только через `[needed:...]`; он никогда не evidence.
- Source ID уникален. Старый source не переиспользуется для нового содержимого.

Manifest делает ссылку разрешимой до паспорта источника. Он не проверяет сам внешний файл повторно; для этого ingestion должен сверить bytes с `content_hash`.

## decision-history.jsonl

Каждая строка — JSON event:

```json
{
  "sequence": 1,
  "recorded_at": "2026-08-12T10:00:00+05:00",
  "actor": "role-or-agent-id",
  "action": "BASELINE",
  "question_id": 1,
  "question_fingerprint": "sha256:...",
  "state": {
    "status": "UNASSESSED",
    "answer": "",
    "evidence": "",
    "depends_on": "",
    "semantic_review": "NOT_REQUIRED"
  },
  "previous_event_hash": "GENESIS",
  "event_hash": "sha256:..."
}
```

`event_hash` считается от канонического JSON всех полей, кроме самого `event_hash`. Следующее событие содержит его в `previous_event_hash`.

Переходы:

- первое событие каждого ID — `BASELINE`;
- `UPDATE` обязан изменить state и сбрасывает принятый статус в `UNREVIEWED`;
- `SEMANTIC_REVIEW` меняет только `UNREVIEWED -> REVIEWED`, содержит `reviewer` и непустой `basis`;
- последнее state каждого ID байт-в-байт совпадает с текущей CSV-строкой.

Переписывание старого события без пересчёта хвоста обнаруживается. Пересчёт всей локальной цепочки обнаружим только при сравнении с ранее опубликованным head hash; поэтому hash-chain — tamper-evident журнал, а не цифровая подпись.

## Корни Незнания

Корень — достижимый из `PENDING_CONTEXT` незакрытый ID без дальнейшей незакрытой зависимости. Ранжирование считает число различных зависимых `PENDING_CONTEXT`; это разблокирующий охват, не бизнес-ценность.

## Миграция

`manage_decision_register.py migrate` принимает старые двух- и пятиколоночные файлы, создаёт четыре канонических файла и `migration-report.tsv`. Legacy answer/evidence получают source type `legacy_text` и hash; это доказательство существования старого текста, а не истинности claim. Принятые строки становятся `UNREVIEWED` и не проходят `--require-reviewed` до отдельного review event.

## Готовность

Обычный validate может завершиться кодом `0` с marker `STRUCTURALLY_VALID_SEMANTICALLY_UNREVIEWED`. Definition of Done требует отдельного запуска с `--require-reviewed`; только записанный event, а не устное утверждение, закрывает этот gate.

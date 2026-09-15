# Feasibility, Coverage And Convergence Gates

## Назначение

Этот контракт не доказывает инженерную надёжность. Он не даёт формальной непохожести вытеснить пригодность и делает путь к shortlist проверяемым.

Порядок неизменен:

```text
target action
→ constraint ledger
→ feasibility gate
→ coverage gate
→ semantic review
→ evidence matrix
→ Pareto shortlist
→ prototype tests
```

## Контролируемые Категории

Категории используют стабильные ID. Конкретный материал или процесс раскрывается в механизме и evidence.

### `primary_material_family`

`cellulose`, `wood`, `metal`, `rigid_polymer`, `elastomer`, `textile`, `glass`, `ceramic`, `mineral_composite`, `bio_material`.

Электроника не является материалом. Активная электронная функция описывается в `mechanism`, а основной конструкционный материал остаётся в этом поле.

### `primary_fabrication_process`

`fold_score`, `laser_cut`, `sheet_bend`, `machining`, `casting`, `sewing`, `additive_manufacturing`, `lamination`, `mechanical_assembly`, `print_coat`.

### `primary_physical_behavior`

`rigid`, `elastic`, `weighted_stable`, `foldable_transformable`, `articulated_rotating`, `magnetic_reconfigurable`, `optical_dynamic`, `soft_tactile`.

### `interaction_mode`

`observe`, `rotate`, `unfold`, `press`, `rearrange`, `assemble`, `touch`, `trigger`.

## Ограничения

Каждое ограничение получает:

```json
{"id": "c_environment", "kind": "hard", "statement": "Работает без сети", "source": "user"}
```

- `hard` нельзя нарушать или предлагать ослабить;
- `soft` можно обсуждать как trade-off;
- `unknown` требует отдельной проверки.

В концепции каждое ограничение получает `pass`, `unknown` или `fail`. Концепция с `fail` не проходит структурный gate. Концепция с `unknown` по `hard` может остаться исследовательской, но не входит в shortlist.

## Критерии И Оценки

Критериев должно быть 3–7. Обязателен `outcome_fit`. Вес — целое число от 1 до 5. Любая оценка трактуется как «больше = лучше».

```json
{"id": "outcome_fit", "name": "Попадание в целевое действие", "weight": 5}
```

Каждая концепция получает по всем критериям:

```json
{"criterion_id": "outcome_fit", "score": 4, "confidence": "medium", "evidence": "Предположение: текст виден с расстояния одного метра"}
```

`score` без `evidence` запрещён. Низкая уверенность не превращается в факт от итоговой суммы.

## Полная Схема Карточки

```json
{
  "target_action": "Сотрудник за несколько секунд выбирает подходящий режим",
  "constraints": [
    {"id": "c_network", "kind": "hard", "statement": "Не требует сети", "source": "user"}
  ],
  "decision_criteria": [
    {"id": "outcome_fit", "name": "Попадание в целевое действие", "weight": 5},
    {"id": "production_ease", "name": "Простота изготовления", "weight": 3},
    {"id": "updateability", "name": "Простота обновления", "weight": 2}
  ],
  "coverage_targets": {
    "primary_material_family": 4,
    "primary_fabrication_process": 4,
    "primary_physical_behavior": 4,
    "interaction_mode": 4
  },
  "concepts": [
    {
      "id": "c1",
      "name": "Короткое имя",
      "target_action": "Что делает или понимает человек",
      "user_value": "Какую отдельную ценность даёт направление",
      "mechanism": "Как объект вызывает действие",
      "primary_material_family": "cellulose",
      "primary_fabrication_process": "fold_score",
      "primary_physical_behavior": "foldable_transformable",
      "interaction_mode": "unfold",
      "difference_rationale": "Почему это не косметический дубль",
      "use_conditions": "Где и как работает",
      "production_complexity": "low",
      "batch_assumption": "20 экземпляров",
      "relative_cost": "low",
      "cost_confidence": "low",
      "cost_drivers": ["Ручная биговка", "Печать малого тиража"],
      "risks": ["Сгибы изнашиваются"],
      "constraint_results": [
        {"constraint_id": "c_network", "status": "pass", "evidence": "Механизм полностью механический"}
      ],
      "criterion_scores": [
        {"criterion_id": "outcome_fit", "score": 4, "confidence": "medium", "evidence": "Предположение до прототипа"},
        {"criterion_id": "production_ease", "score": 5, "confidence": "medium", "evidence": "Нужны печать, рез и биговка"},
        {"criterion_id": "updateability", "score": 3, "confidence": "medium", "evidence": "Для обновления нужна новая печать"}
      ],
      "prototype_check": {
        "hypothesis": "Пользователь раскрывает нужную грань без инструкции",
        "observable": "Не менее 4 из 5 участников находят раздел за 10 секунд",
        "failure_condition": "Два участника или больше не понимают механику"
      }
    }
  ],
  "shortlist": [
    {"id": "c1", "decision_reason": "Лучший trade-off простоты и обновляемости", "next_test": "Бумажный прототип 1:1"}
  ],
  "semantic_review": {
    "status": "pass",
    "performed_by": "assistant",
    "reviewed_axes": ["material_family", "fabrication_process", "physical_behavior", "interaction_mode", "mechanism", "constraints", "shortlist"],
    "notes": "Синонимы объединены, косметические дубли удалены, trade-offs проверены"
  }
}
```

## Coverage Gate

Default target — четыре разные категории на каждую ось среди 5–7 концепций. Это coverage, а не требование уникальности каждого значения.

Повтор допустим, когда:

1. концепция проходит feasibility;
2. `user_value` и механизм действительно отличаются;
3. `difference_rationale` объясняет отличие;
4. общая цель покрытия всё ещё достигнута.

Снижение target допустимо только из-за явного ограничения и фиксируется в `semantic_review.notes`.

## Semantic Review

Строковый валидатор не распознаёт смысловые синонимы. До `Definition Of Done` проверьте:

1. конкретные материалы не выданы за разные семьи;
2. вторичные операции не выданы за разные primary process;
3. поведение не переименовано без физического отличия;
4. одинаковое действие пользователя не замаскировано разными глаголами;
5. механизм и user value не повторяются под новыми прилагательными;
6. hard constraints не нарушены и не предложены к ослаблению;
7. shortlist не содержит доминируемое решение;
8. оценки отделяют доказательство от предположения.

## Pareto Shortlist

Концепция `A` доминирует `B`, если `A` имеет не меньший score по каждому критерию и больший хотя бы по одному. Доминируемая концепция не входит в shortlist.

Shortlist обязан включать хотя бы одну feasible-концепцию с максимальной взвешенной суммой `score × weight`. Остальные финалисты показывают недоминируемые trade-offs, а не заменяют лучший по заданным весам вариант.

Pareto-проверка не отменяет уверенность и evidence. При низкой уверенности следующий шаг — сравнительный прототип, а не производственное решение.

## Что Проверяет Скрипт

`scripts/validate_concept_fan.py` проверяет:

- количество 5–7;
- строгие типы и enum-категории;
- coverage targets;
- полное покрытие constraints и decision criteria;
- отсутствие концепций с `fail`;
- запрет `unknown` по hard constraint в shortlist;
- недоминируемость shortlist;
- структуру prototype tests и economics assumptions;
- заполненную semantic review.

Он не доказывает физическую прочность, нормативное соответствие, рыночную стоимость или смысловую оригинальность.

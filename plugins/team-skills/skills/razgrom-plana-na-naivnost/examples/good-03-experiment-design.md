# Хороший Пример: Experiment Design

## Вход

Пользователь вставляет текст: “Мы проверим идею через A/B тест: половине пользователей покажем новый onboarding, потом сравним conversion rate. Если будет плюс, сразу выкатываем всем.”

Пользователь просит: “Разбей как постановщик интернет-экспериментов и growth-аналитик.”

## Ожидаемое Поведение

Codex применяет forensic-аудит к эксперименту: проверяет hypothesis, randomization, sample size logic, eligibility, exposure, attribution window, novelty effect, metric definition, guardrails, contamination, rollout criteria и rollback. Если в тексте этого нет, он прямо говорит, что это не experiment design, а обряд с названием A/B.

Codex объясняет условные риски: без расчёта численности нельзя подтвердить достаточную мощность; без определения denominator сравнение conversion rate может оказаться некорректным; при разном составе групп смешение сегментов может исказить эффект; без измерения long-term retention можно пропустить его ухудшение; rollout без правила решения рискует принять шум за causal impact. Данных для утверждений, что выборка уже недостаточна или retention действительно ухудшился, во входе нет. Затем показывает практику сильных команд: preregistered decision rule, primary metric, guardrail metrics, cohort split, instrumentation QA, staged rollout и post-test readout.

## Нельзя

Нельзя спорить с A/B тестом как форматом вообще. Нужно атаковать конкретные пропуски в дизайне. Нельзя обещать статистическую значимость без входных чисел.

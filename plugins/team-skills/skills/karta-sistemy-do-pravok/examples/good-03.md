# Contradiction Блокирует Stable Docs

## Вход

«Документ утверждает route X, но датированный runtime config показывает route
Y. Обнови карту знаний и stable docs.»

## Ожидаемое Поведение

Skill добавляет `claim_contradicted`, сохраняет оба evidence sources, блокирует
`document_promoted` для зависимого документа и открывает next action на
уточнение действующего route. Projection показывает contradiction явно.

## Нельзя

- сглаживать конфликт формулировкой «возможно используются оба» без evidence;
- вручную исправлять projection как источник истины;
- продвигать документ со state `contradicted` или `stale`.

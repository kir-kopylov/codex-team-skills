# Claim, Evidence И Unknown

## Вход

«В source найден вызов Desktop → WebAPI. Зафиксируй знание, но неизвестно,
работает ли этот route в production.»

## Ожидаемое Поведение

Skill создаёт отдельные `claim_proposed`, `evidence_attached` и
`claim_supported` для static source, затем открывает `unknown_opened` о current
deployment с точным missing evidence, owner и next action. Events передаются
через `goalrt domain emit`.

## Нельзя

- объединять claim и evidence в одну неподтверждаемую фразу;
- объявлять production currentness доказанной;
- закрывать unknown догадкой.

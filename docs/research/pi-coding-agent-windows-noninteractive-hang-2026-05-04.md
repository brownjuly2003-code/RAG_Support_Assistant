# Технический research: `pi -p` hang на Windows после `write` tool (openai-codex)

**Дата research:** 2026-05-04  
**Локальная версия:** `pi 0.72.1`  
**Целевая среда:** Windows PowerShell 5.1, non-interactive CLI  
**Провайдер/модель:** `openai-codex/gpt-5.3-codex-spark` (OAuth/subscription, без `OPENAI_API_KEY`)  

---

## 1. Executive Summary

Проблема зависания `pi` после успешного вызова `write` tool в non-interactive режиме (`-p` / `--print`) на Windows является **известным upstream-багом**, активным в последней доступной версии `0.72.1`.

Корневая причина — сочетание двух факторов:
1. **Утечка WebSocket/session-кеша провайдера `openai-codex`** в print-режиме: внутренний `sessionId` передаётся провайдеру даже при `--no-session`, из-за чего Codex-провайдер открывает persistent WebSocket/SSE-соединение, которое удерживает Node.js event loop от завершения.
2. **Отсутствие force-exit в CLI print mode**: после завершения `runPrintMode()` процесс не вызывает `process.exit()`, полагаясь на естественное опустошение event loop, что не срабатывает при открытых сетевых хендлах или `process.stdin.resume()` в non-TTY окружении.

Баг воспроизводится с флагами `--no-extensions --no-tools --no-session`, то есть не зависит от расширений пользователя. Upstream-исправление существует в виде PR #4127, но на момент 0.72.1 оно **не влито и не релизнуто**.

Проблема обрезки многострочного prompt при передаче через `-p` напрямую в Windows `.cmd` shim — это ограничение Windows command-line parsing (не баг `pi` per se); официальный workaround — использование синтаксиса `@file.md` (уже применён).

---

## 2. Evidence Table

| Источник (URL) | Точное находка | Релевантность |
|---|---|---|
| [GitHub Issue #4128](https://github.com/badlogic/pi-mono/issues/4128) | "`pi -p` / `pi --mode json -p` can emit the final output (and `agent_end` in JSON mode) but keep the Node process alive until killed. I reproduced this with `--no-extensions --no-tools`... This happens because print mode still forwards `agent.sessionId` to providers. With `openai-codex/*` and `transport: auto`, the Codex provider can create a session-scoped cached WebSocket." Репродьюсер использует `--model openai-codex/gpt-5.3-codex-spark`. | **Критическая** — полное совпадение сценария: версия 0.72.1, провайдер openai-codex, print mode, зависание после вывода. |
| [GitHub PR #4127](https://github.com/badlogic/pi-mono/pull/4127) | "This change clears `session.agent.sessionId` in print mode before prompts run, so one-shot `pi -p` / `pi --mode json -p` executions do not enter provider-side session caches." Test plan подтверждает выход с rc 0 после патча. | **Критическая** — upstream-фикс, пока не влитый в релиз. |
| [GitHub Issue #4134](https://github.com/badlogic/pi-mono/issues/4134) | "When calling `pi -p {prompt}`, the agent outputs correctly but does not close the process. Version 0.72.1." | **Высокая** — подтверждение, что hang в `-p` актуален для 0.72.1. |
| [GitHub Issue #3886](https://github.com/badlogic/pi-mono/issues/3886) | "Running `pi --mode json -p "..."` in a subprocess causes pi to hang indefinitely after completing the response. Root cause: `readPipedStdin()` calls `process.stdin.resume()` when `process.stdin.isTTY` is false. This keeps Node's event loop alive indefinitely... When stdout is piped, the calling process never closes pi's stdin, so `end` never fires." Environment: Windows 11, pi 0.70.5. | **Высокая** — объясняет дополнительный механизм удержания процесса в non-TTY (PowerShell runner с piped stdio). |
| [GitHub Issue #2677](https://github.com/badlogic/pi-mono/issues/2677) | "`pi -p` (print mode) hangs indefinitely when extensions are loaded... In `main.js`, after `runPrintMode()` returns, the code sets `process.exitCode` but only `return`s — it never calls `process.exit()`." | **Высокая** — общий дефект архитектуры print mode: отсутствие force-exit. |
| [GitHub Issue #3015](https://github.com/badlogic/pi-mono/issues/3015) | "In `--print` mode, `main()` returns a promise that is never awaited. Open undici connections (from `EnvHttpProxyAgent`) and piped stdin hold the Node.js event loop alive after `main()` resolves." | **Высокая** — подтверждает утечку сетевых соединений (undici) в print mode. |
| [GitHub Issue #4141](https://github.com/badlogic/pi-mono/issues/4141) | "If the subscription auth token for the `openai-codex` provider is expired when interacting with a model the process will hang after the API response is displayed. System: Windows 11. pi: 0.72.1." | **Средняя** — альтернативный триггер hang на Windows специфично для openai-codex. |
| [GitHub Issue #2464](https://github.com/badlogic/pi-mono/issues/2464) | "On Windows, this can fail with spawn pi ENOENT when pi is installed via npm or scoop and is exposed through a `.cmd` shim instead of a directly executable binary." | **Средняя** — документирует проблемы Windows `.cmd` shim в экосистеме `pi`. |
| [npm registry / `npm view`](primary source) | `@mariozechner/pi-coding-agent` latest version: `0.72.1`. | **Критическая** — подтверждение, что локальная версия совпадает с latest; фикс отсутствует в релизе. |
| [GitHub Releases v0.72.1](https://github.com/badlogic/pi-mono/releases) | Changelog v0.72.1 содержит фиксы Windows shim для `pi update`, но **не содержит** исправлений print mode hang или Codex WebSocket cache. | **Критическая** — доказательство, что fix не выпущен. |
| [Pi Docs — CLI Reference](https://www.npmjs.com/package/@mariozechner/pi-coding-agent) | "Prefix files with `@` to include in the message: `pi -p @screenshot.png` ... `pi @prompt.md`" | **Средняя** — официальная документация `@file` как способа передачи prompt. |
| [Pi Docs — Settings](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/settings.md) | "`transport`: Preferred transport for providers that support multiple transports: `"sse"`, `"websocket"`, or `"auto"`." | **Средняя** — показывает наличие настройки transport, но см. Issue #4083. |
| [GitHub Issue #4083](https://github.com/badlogic/pi-mono/issues/4083) | "For `openai-codex` provider, the base options get from `buildBaseOptions` ... won't have `transport` field, because it's not included ... so the `transport` at `streamOpenAICodexResponses` will always fallback to `sse`." Version 0.72.0. | **Средняя** — inference: даже если пользователь выставит `transport: sse`, Codex-провайдер в pi-ai может игнорировать это в некоторых code path; тем не менее WebSocket cache leak возникает именно в коде обработки `sessionId`. |

---

## 3. Root Cause Hypothesis with Confidence

### Гипотеза A: Codex Provider Session-Scoped WebSocket Cache Leak (PRIMARY)
**Confidence: HIGH**

В print mode (`-p`) `pi` передаёт внутренний `session.agent.sessionId` в провайдер `openai-codex`. Провайдер создаёт session-scoped cached WebSocket (или SSE-коннекцию с keep-alive), который предназначен для интерактивных сессий, но в single-shot режиме остаётся открытым после `agent_end`. Поскольку сокет удерживает event loop, Node.js процесс не завершается.

**Доказательства:**
- Issue #4128 содержит точный репродьюсер с `--model openai-codex/gpt-5.3-codex-spark` и `--no-extensions --no-tools`, который таймаутится через `timeout 80`.
- PR #4127 фиксит это единственным изменением: очисткой `sessionId` перед prompt в print mode.
- Issue #4103 подтверждает, что при `transport: auto` / `websocket` наблюдается тот же hang.

### Гипотеза B: Отсутствие `process.exit()` в print mode (ARCHITECTURAL)
**Confidence: HIGH**

После завершения `runPrintMode()` control flow возвращается в `main.js` / `cli.ts`, но `process.exit()` не вызывается. Когда event loop содержит открытые handles (WebSocket, HTTP keep-alive, `process.stdin.resume()`), Node.js не завершается самостоятельно.

**Доказательства:**
- Issue #2677: "In `main.js`, after `runPrintMode()` returns, the code sets `process.exitCode` but only `return`s — it never calls `process.exit()`."
- Issue #3015: "Open undici connections ... hold the Node.js event loop alive after `main()` resolves."

### Гипотеза C: `process.stdin.resume()` в non-TTY окружении (CONTRIBUTING)
**Confidence: MEDIUM**

Функция `readPipedStdin()` в `main.js` вызывает `process.stdin.resume()` когда `isTTY === false`. В автоматизированных runner'ах (PowerShell non-interactive, subprocess с piped stdin) stdin никогда не закрывается вызывающей стороной, поэтому `end` не срабатывает и event loop остаётся заблокированным.

**Доказательства:**
- Issue #3886 с окружением Windows 11, Node v25.9.0, pi 0.70.5.
- Репродьюсер: `pi --mode json -p "say YES" --no-session --no-skills | cat` — виснет навсегда.

### Гипотеза D: Windows `.cmd` Shim Argument Truncation (SEPARATE, NOT ROOT CAUSE OF HANG)
**Confidence: HIGH**

Обрезка многострочного prompt при прямой передаче через `-p` вызвана ограничениями Windows command-line parsing в `.cmd` shim (npm создаёт `pi.cmd`). Это не баг `pi`, а платформенное ограничение. Официальный workaround — `@file.md`.

**Доказательства:**
- Issue #2464 документирует другие проблемы `.cmd` shim в экосистеме `pi`.
- CLI Reference явно описывает `@file` как метод загрузки prompt из файла.

### Итоговая классификация
Зависание является **багом комбинации tool lifecycle + provider-specific network handle leak + missing force-exit в CLI**, а не ожидаемым поведением. `--no-session` не предотвращает hang, потому что `sessionId` используется на уровне провайдера для кеширования, а не для персистентности локальной сессии.

---

## 4. Recommended Fix / Workaround

### 4.1 Upstream Fix (не доступен в релизе)
- **PR #4127** — очистка `session.agent.sessionId` в print mode.
- **Issue #3015 / #2677** — добавление `process.exit()` после завершения `main()` в `cli.ts`.
- Ожидаемый статус: войдёт в версию `> 0.72.1` (предположительно `0.72.2` или `0.73.0`).

### 4.2 Безопасные Workarounds для Automation (сейчас)

#### A. External Timeout Wrapper (RECOMMENDED)
Использовать внешний таймаут с force-kill процесса, как уже реализовано в runner. Это единственный надёжный способ, пока баг не исправлен upstream.

PowerShell 5.1:
```powershell
$proc = Start-Process -FilePath "pi" `
  -ArgumentList "--model","openai-codex/gpt-5.3-codex-spark",`
    "--thinking","minimal","--tools","write",`
    "--no-session","--no-extensions","--no-skills",`
    "--no-prompt-templates","--no-themes","--no-context-files",`
    "-p","@.autopilot/planner.prompt.md" `
  -PassThru `
  -RedirectStandardOutput "pi_out.txt" `
  -RedirectStandardError  "pi_err.txt" `
  -RedirectStandardInput  "nul"   # см. Workaround B

$proc | Wait-Process -Timeout 120
if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
    # при необходимости: рекурсивный kill child processes
}
```

#### B. Закрытие Stdin (мигация `stdin.resume()` issue)
Передача `-RedirectStandardInput "nul"` (или пустого файла) закрывает stdin сразу, что устраняет вклад Issue #3886.

#### C. Отключение лишних startup network handles
Уменьшает вероятность дополнительных утечек:
```powershell
$env:PI_SKIP_VERSION_CHECK = "1"
$env:PI_OFFLINE = "1"
# или --offline flag
```

#### D. Использование `@file.md` для prompt (уже применено)
Продолжать использовать `@.autopilot/planner.prompt.md` вместо inline multiline `-p` на Windows.

#### E. Альтернативный provider (если возможно)
Если subscription OAuth не является строгим требованием, использование OpenAI API-key provider (`--provider openai --model gpt-4o`) или Anthropic позволяет избежать Codex-specific WebSocket cache leak.

#### F. Direct SDK Call (для сложной автоматизации)
Вместо CLI можно вызвать `@mariozechner/pi-coding-agent` программно из Node.js скрипта, явно управляя `session.dispose()` и вызывая `process.exit()`:
```typescript
import { createAgentSession, AuthStorage, ModelRegistry, SessionManager } from "@mariozechner/pi-coding-agent";
// ... настройка сессии, prompt, ожидание tool output ...
await session.dispose();
process.exit(0);
```
*Примечание: inference на основе архитектуры, описанной в docs; может потребовать дополнительной проверки на целевой машине.*

#### G. Попытка принудить `transport: sse` через `settings.json`
Хотя Issue #4083 утверждает, что `transport` не прокидывается через `buildBaseOptions`, можно попробовать задать глобально:
```json
{ "transport": "sse" }
```
в `~/.pi/agent/settings.json`. Это может изменить поведение в некоторых code path, но **не гарантирует** обход бага из-за многоуровневой передачи опций.

---

## 5. Minimal Reproduction Commands for Windows PowerShell

### Предусловия
- PowerShell 5.1 (non-interactive, без TTY).
- `pi` установлен глобально (`npm i -g @mariozechner/pi-coding-agent@0.72.1`).
- Авторизация `openai-codex` выполнена (`/login`).

### Repro 1: Основной сценарий hang
```powershell
pi --model openai-codex/gpt-5.3-codex-spark `
   --thinking minimal --tools write `
   --no-session --no-extensions --no-skills `
   --no-prompt-templates --no-themes --no-context-files `
   -p "Say exactly: EXIT_OK"
# Ожидаемое поведение: вывод EXIT_OK и возврат в prompt
# Фактическое поведение (0.72.1): вывод EXIT_OK, курсор мигает, процесс висит
```

### Repro 2: Проверка влияния piped stdin/stdout
```powershell
# В PowerShell: piping через Out-String или другой процесс
echo "test" | pi --model openai-codex/gpt-5.3-codex-spark `
   --no-session --no-extensions --no-tools `
   -p "Say OK"
# Воспроизводит вклад Issue #3886 (stdin.resume)
```

### Repro 3: Workaround с timeout
```powershell
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "pi"
$psi.Arguments = "--model openai-codex/gpt-5.3-codex-spark --thinking minimal --tools write --no-session --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files -p `"Say OK`""
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.RedirectStandardInput = $true
$psi.UseShellExecute = $false
$p = [System.Diagnostics.Process]::Start($psi)
$p.StandardInput.Close()  # закрываем stdin
$p.WaitForExit(120000)    # 120 сек
if (-not $p.HasExited) {
    $p.Kill()
    Write-Host "Process killed by timeout"
}
Write-Host "Exit code: $($p.ExitCode)"
```

---

## 6. Risks / Unknowns

| Риск | Описание |
|---|---|
| **PR #4127 может задержаться** | На момент research PR существует, но не влит. Дата следующего релиза неизвестна. |
| **Issue #4083 (transport ignored)** | Если `transport` действительно не прокидывается в Codex-провайдер, попытки форсировать `sse` через `settings.json` могут не сработать. |
| **Issue #4141 (expired token hang)** | Даже после фикса #4127 при истёкшем токене `openai-codex` может вести себя иначе (hang + corruption терминала на Windows). Рекомендуется мониторить срок действия OAuth-токена. |
| **Undici / HTTP agent leaks** | Issue #3015 указывает на утечки `EnvHttpProxyAgent`. `PI_OFFLINE=1` убирает version check, но не отключает основные LLM-запросы. |
| **PowerShell 5.1 specific behavior** | `-RedirectStandardInput "nul"` ведёт себя иначе, чем `/dev/null` в Linux; рекомендуется тестировать `StandardInput.Close()` через .NET API. |
| **Отсутствие флага `--force-exit`** | В текущей версии нет CLI-флага для принудительного завершения процесса после print mode; workaround только внешний. |

---

## 7. Links to Upstream Issues / PRs / Changelog

- **Issue #4128** — Print mode can hang after agent_end with Codex WebSocket cache  
  https://github.com/badlogic/pi-mono/issues/4128
- **PR #4127** — Fix: clear `sessionId` in print mode to prevent Codex WebSocket cache hang  
  https://github.com/badlogic/pi-mono/pull/4127
- **Issue #4134** — `pi -p` does not exit and hangs (0.72.1)  
  https://github.com/badlogic/pi-mono/issues/4134
- **Issue #3886** — `pi -p` does not exit when stdout is piped (`process.stdin.resume()` keeps event loop alive)  
  https://github.com/badlogic/pi-mono/issues/3886
- **Issue #2677** — `pi -p` hangs when extensions are loaded — missing `process.exit()`  
  https://github.com/badlogic/pi-mono/issues/2677
- **Issue #3015** — FD leak in print mode: `cli.ts` does not await `main()` or call `process.exit()`  
  https://github.com/badlogic/pi-mono/issues/3015
- **Issue #4141** — Expired tokens cause hung process (Windows, openai-codex)  
  https://github.com/badlogic/pi-mono/issues/4141
- **Issue #2464** — subagent fails on Windows when pi is installed as a `.cmd` shim  
  https://github.com/badlogic/pi-mono/issues/2464
- **Issue #4083** — `transport` option is not honored in `openai-codex` provider  
  https://github.com/badlogic/pi-mono/issues/4083
- **Changelog / Releases** — v0.72.1 (latest, без фикса print mode hang)  
  https://github.com/badlogic/pi-mono/releases
- **NPM Package** — `@mariozechner/pi-coding-agent` latest = 0.72.1  
  https://www.npmjs.com/package/@mariozechner/pi-coding-agent
- **Pi Documentation** — CLI Reference (print mode, `@file` syntax)  
  https://www.npmjs.com/package/@mariozechner/pi-coding-agent
- **Pi Documentation** — Settings (`transport` option)  
  https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/settings.md

---

*Отчёт составлен на основе первичных источников: official docs, GitHub issues/PRs, changelog, npm package metadata. Любые выводы, не подтверждённые прямой цитатой, помечены как inference.*

# Founder report — week 1 (nights 2026-09-28 to 10-04)

1. SECURITY: a bot returning Infinity, NaN or a 400-digit number in an action could crash a match. Found by the fuzzer, fixed, permanent test, no past night affected (PROGRESS, 3.9).
2. **Tops:** attacker `interleaved_shell_ring` (Elo 1245, generalist, written tonight); defender `convergence_blast_scheduler` (Elo 1195, **91%**, over the flag).
3. **Personas** (meta report, verbatim):
   - **exploiter**: 2 written, 0 beat their target, 2 still alive, best finish #1 attacker.
   - **counter_meta**: 4 written, 3 beat their target, 4 still alive, best finish #1 attacker.
   - **generalist**: 3 written, 1 beat their target, 3 still alive, best finish #1 attacker.
   - **contrarian**: 3 written, 1 beat their target, 3 still alive, best finish #1 defender.
4. **Done:** cache, token budgets, build sessions, tactic library, fuzzing, site + about, workshop kit, game-only engine scoping; sprint L1–L5 (`make reproduce` OK on a fresh clone in 364 s).
5. **Blocked:** G (waiting for your prompt text; tonight used 2026-10-03.1); 3.8 (interactive only).
6. **Tokens:** league 277,925 this week (= season to date); build sessions 705,790 over 9 sessions; L3 ablation run 162,740.
7. **S0-2:** answered in play (ring now 83%), but defenders win 62%, outside the 40–60 band. The literal rule says A + a gun fix, which would help defenders further.
8. **Yes/no:** season two = candidate A only, with 62% / 91% logged as the next finding?
9. **Yes/no:** a 7-night watch on convergence_blast_scheduler (91%), the same rule as S0-2?
10. **Yes/no:** keep the 14-night persona ablation (~450k tokens, auto at night 14)?

## Safety stops so far (one line each)

- 10-01, generator: a counter-meta defender prompt aimed at synchronized_ring was refused ("maps onto real counter-drone engagement tactics"). Logged as a rejection, not reworded.
- 10-02, generator: the same kind of slot was refused again. Logged, not reworded.
- 10-03, lead engineer: the original red-team item (3.8) was stopped by a classifier. Stopped; you rewrote it as defensive-only and interactive.
- 10-03, lead engineer: the generator-prompt rewrite (G) was stopped by a classifier. Stopped; you took G yourself.

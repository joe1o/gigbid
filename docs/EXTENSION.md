# Signature extension X2: proposal experiments (A/B test)

## Question
Does the way a proposal opens change whether clients reply?

## Design
Two writing strategies, each a versioned prompt; everything else in the bid graph is identical
(same evidence, critic, claim verification, compliance and price):

| Arm | Prompt | Strategy |
|---|---|---|
| A (control) | `agent/prompts/writer.md` | open with the client's problem, 1-2 pieces of evidence, plan, next step |
| B (variant) | `agent/prompts/writer_b.md` | short; open with one sharp question about the client's problem, then the single best piece of evidence |

The Writer's prompt is chosen by configuration (`GIGBID_WRITER_PROMPT`), so the experiment needs
no code change. Both arms ran on the same good-fit dev jobs (30 per arm, all three personas),
drafts were auto-approved (evaluation only) and GigSim's simulated clients decided whether to
reply. Runner: `evals/runners/ab_test.py`. Result file: `evals/results/ab_test.json`.

## Test
Two-proportion z-test on reply rate, two-sided, alpha 0.05.

## Results
| Arm | Replied / sent | Reply rate | Average words |
|---|---|---|---|
| A | 18 / 30 | 60% | 146 |
| B | 20 / 29 | 69% | 126 |

Difference +9 points, z = 0.72, p = 0.47. **Not significant.**

## Conclusion
Strategy B was shorter and got slightly more replies, but with about 30 proposals per arm a
9-point difference is well within chance. To detect a 9-point lift with 80% power at this reply
rate, each arm would need roughly 450 proposals. A stays the default; the experiment harness is
in place to run the larger test. A limitation is that GigSim's simulated clients reward specific
openings, concrete numbers and sensible length in both arms, so they may not reflect how real
clients react to a question-led opening.

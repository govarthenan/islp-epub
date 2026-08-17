export const meta = {
  name: 'islp-math-verify',
  description: 'Adversarially check every transcribed expression against the printed page',
  phases: [
    { title: 'Refute', detail: 'one agent per batch: try to find a difference in each pair' },
  ],
}

const RESULT = {
  type: 'object',
  additionalProperties: false,
  required: ['batch', 'checked', 'verdicts'],
  properties: {
    batch: { type: 'string' },
    checked: { type: 'integer' },
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'verdict', 'issue', 'corrected_latex'],
        properties: {
          id: { type: 'string' },
          verdict: {
            type: 'string',
            enum: ['same', 'cosmetic', 'wrong'],
            description: 'same = identical mathematics; cosmetic = a difference of spacing, '
              + 'delimiter size or font that does not change the meaning; wrong = the '
              + 'mathematics differs',
          },
          issue: { type: 'string', description: 'empty when same; otherwise the single clearest difference' },
          corrected_latex: { type: 'string', description: 'empty unless verdict is wrong' },
        },
      },
    },
  },
}

const INSTRUCTIONS = (batchPath, index) => `You are checking transcriptions of mathematics from
the textbook "An Introduction to Statistical Learning with Applications in Python". Someone
else read each expression out of the printed page and wrote LaTeX for it. Your job is to
**find where they got it wrong**.

Work from \`${batchPath}\`, relative to the repository root which is your working directory.
Read it with the Read tool. Each entry has:

  id       the identifier to key your verdict on
  compare  a PNG in two halves, separated by a horizontal rule:
             TOP    - the expression cut straight out of the printed page
             BOTTOM - the same expression re-typeset from the candidate LaTeX
  latex    the candidate LaTeX itself
  characters  the characters the PDF's text layer gave up for that expression. The symbols
              are reliable even where the structure is not, so a symbol present here and
              absent from the LaTeX is strong evidence of a dropped term.

For each entry, read the comparison image and assume there IS a difference until you have
checked, one by one:

  * every symbol, including every Greek letter and every operator;
  * every subscript and superscript, and which base each attaches to;
  * the limits above and below every sum, product and integral;
  * numerator against denominator, in that order, for every fraction;
  * every accent - hat, bar, tilde - and what it sits over;
  * every delimiter, and what it encloses;
  * upright against italic where it distinguishes an operator name from a variable;
  * the presence of trailing punctuation.

Then give a verdict:

  "same"     the two halves state the same mathematics
  "cosmetic" they differ only in spacing, delimiter size, font choice or line breaking
  "wrong"    the mathematics differs. Give corrected_latex: the whole expression, corrected,
             in the same conventions as the candidate (body only, no dollar signs, no
             equation number, MathJax-compatible).

Be strict about "wrong" and honest about "same". Reporting a difference that is not there
costs as much as missing one that is. If the TOP half is itself cut off or unreadable, say so
in issue and use verdict "cosmetic" rather than inventing a correction.

Write your verdicts to \`work/math_verdicts/${String(index).padStart(3, '0')}.json\` with the
Write tool as a JSON array of {"id", "verdict", "issue", "corrected_latex"}, then return the
same data in the structured result. Your final message is data, not prose.`

phase('Refute')

log(`verifying ${args.length} batches`)

const results = await parallel(
  args.map((batchPath, index) => () =>
    agent(INSTRUCTIONS(batchPath, index), {
      label: `verify:${index}`,
      phase: 'Refute',
      schema: RESULT,
    })),
)

const good = results.filter(Boolean)
const verdicts = good.flatMap((r) => r.verdicts || [])
const counts = verdicts.reduce((acc, v) => {
  acc[v.verdict] = (acc[v.verdict] || 0) + 1
  return acc
}, {})

log(`verdicts: ${JSON.stringify(counts)}`)

return {
  batches: args.length,
  returned: good.length,
  checked: verdicts.length,
  counts,
  wrong: verdicts.filter((v) => v.verdict === 'wrong').map((v) => ({ id: v.id, issue: v.issue })),
}

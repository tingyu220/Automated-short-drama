export interface PriceRuleInput {
  key: string
  name: string
  targetPrice: number
  minPrice: number
  maxPrice: number
  sameDistanceStrategy: string
  enabled: boolean
}

export interface PriceSimulationRow {
  candidate: number
  matched: boolean
  matchedRuleKey: string | null
  ruleName: string | null
  targetPrice: number | null
  distance: number | null
  selectionReason: string
}

function round(value: number): number {
  return Math.round(value * 1000) / 1000
}

export function parseCandidates(text: string): number[] {
  return text
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map(Number)
    .filter((value) => Number.isFinite(value))
}

export function simulatePriceCandidates(
  candidates: number[],
  rules: PriceRuleInput[]
): PriceSimulationRow[] {
  const enabled = rules.filter((rule) => rule.enabled)
  return candidates.map((candidate) => {
    const matches = enabled.filter(
      (rule) => rule.minPrice <= candidate && candidate <= rule.maxPrice
    )
    if (matches.length === 0) {
      return {
        candidate,
        matched: false,
        matchedRuleKey: null,
        ruleName: null,
        targetPrice: null,
        distance: null,
        selectionReason: "NO_MATCH"
      }
    }

    matches.sort((a, b) => {
      const distanceDiff =
        Math.abs(candidate - a.targetPrice) -
        Math.abs(candidate - b.targetPrice)
      if (distanceDiff !== 0) return distanceDiff
      const higherFirst =
        a.sameDistanceStrategy === "HIGHER_PRICE_FIRST" ||
        b.sameDistanceStrategy === "HIGHER_PRICE_FIRST"
      return higherFirst
        ? b.targetPrice - a.targetPrice
        : a.targetPrice - b.targetPrice
    })

    const best = matches[0]
    return {
      candidate,
      matched: true,
      matchedRuleKey: best.key,
      ruleName: best.name,
      targetPrice: best.targetPrice,
      distance: round(Math.abs(candidate - best.targetPrice)),
      selectionReason: "距离目标价最近；同距离按策略排序"
    }
  })
}

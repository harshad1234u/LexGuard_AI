import type { Provenance, ReasoningResult } from '../../types/api'

const PROVIDER_NAMES: Record<string, string> = {
  gemini: 'Gemini',
  nemotron: 'Nemotron',
}

const name = (provider: string | null | undefined) =>
  provider ? (PROVIDER_NAMES[provider] ?? provider) : null

/**
 * Who did what, stated plainly. The models interpret; the application decides
 * what is verified. There is deliberately no "AI verified" wording here or
 * anywhere else - no model verifies its own output.
 */
export function ProvenanceStrip({
  provenance,
  reasoning,
}: {
  provenance: Provenance | null | undefined
  reasoning: ReasoningResult | null | undefined
}) {
  if (!provenance) return null

  const reasoningText =
    !reasoning || reasoning.status === 'disabled'
      ? 'off'
      : (name(reasoning.provider ?? provenance.reasoning_provider) ?? 'off')

  return (
    <p
      aria-label="How this analysis was produced"
      className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-slate-600"
    >
      <span>
        Analysis: <span className="font-semibold text-slate-800">{name(provenance.provider)}</span>
      </span>
      <span aria-hidden="true">·</span>
      <span>
        Reasoning notes: <span className="font-semibold text-slate-800">{reasoningText}</span>
      </span>
      <span aria-hidden="true">·</span>
      <span>
        Verification: <span className="font-semibold text-slate-800">application-controlled</span>
      </span>
    </p>
  )
}

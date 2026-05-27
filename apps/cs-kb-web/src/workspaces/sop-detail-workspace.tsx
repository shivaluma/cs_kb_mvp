import {
  IconArrowLeft as ArrowLeft,
  IconArrowRight as ArrowRight,
  IconCalendar as Calendar,
  IconChecklist as Checklist,
  IconClock as Clock,
  IconCopy as Copy,
  IconFileText as FileText,
  IconFolder as Folder,
  IconGitBranch as GitBranch,
  IconMessage as MessageSquareText,
  IconSearch as Search,
  IconShieldCheck as ShieldCheck,
} from "@tabler/icons-react";
import type { ElementType, ReactNode } from "react";

import { EmptyPanel, Fact, MacroCopyButton, MetaLine, SectionTitle, TagSummary } from "@/components/common";
import { SourceContextCard } from "@/components/source-context-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import { groupResultsByDisplaySource } from "@/lib/source-display";
import { isDebugUiEnabled } from "@/lib/ui-mode";
import type { Macro, RetrievalResult, SOP } from "@/types";

export function SOPDetailWorkspace({
  copied,
  error,
  loading,
  onAskChat,
  onCopyMacro,
  onOpenCategory,
  onSearchRelated,
  sourceMatch,
  sourceQuery,
  sop,
}: {
  copied: string;
  error: string;
  loading: boolean;
  onAskChat: (question: string) => void;
  onCopyMacro: (macro: Macro) => void;
  onOpenCategory: (sop: SOP) => void;
  onSearchRelated: (query: string) => void;
  sourceMatch?: RetrievalResult | null;
  sourceQuery?: string;
  sop: SOP | null;
}) {
  if (loading) {
    return <EmptyPanel compact icon={FileText} text="Loading the latest published version." title="Opening SOP" />;
  }

  if (error || !sop) {
    return (
      <EmptyPanel
        compact
        icon={FileText}
        text={error || "This SOP is unavailable from the published index."}
        title="SOP unavailable"
      />
    );
  }

  const version = sop.current_version;
  const sections = version.sections;
  const chatPrompt = sop.title;
  const debugEnabled = isDebugUiEnabled();
  const sourceGroup = sourceMatch ? groupResultsByDisplaySource([sourceMatch])[0] : null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
          onClick={() => history.back()}
          type="button"
        >
          <ArrowLeft className="size-4" />
          Back
        </button>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onSearchRelated(sop.title)} type="button" variant="outline">
            <Search data-icon="inline-start" className="size-4" />
            Search related
          </Button>
          <Button onClick={() => onAskChat(chatPrompt)} type="button" variant="outline">
            <MessageSquareText data-icon="inline-start" className="size-4" />
            Ask chat
          </Button>
        </div>
      </div>

      <section className="rounded-xl border bg-card p-4 md:p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{sop.code}</Badge>
              <Badge variant="secondary">Published source of truth</Badge>
              <Badge variant="outline">v{version.version_number}</Badge>
            </div>
            <h2 className="max-w-4xl text-2xl font-semibold tracking-tight md:text-3xl">{sop.title}</h2>
            <p className="mt-3 max-w-4xl text-sm leading-6 text-muted-foreground">{sop.summary}</p>
            <MetaLine
              className="mt-3"
              items={[sop.owner_team, sop.vertical, sop.category, formatDate(sop.updated_at)]}
            />
            <TagSummary className="mt-4" items={[...sop.case_reasons, ...sop.tags, ...sop.audience]} maxItems={6} />
          </div>
          <div className="grid content-start gap-2 sm:grid-cols-3 xl:grid-cols-1">
            <Fact icon={Calendar} label="Effective from" value={formatOptionalDate(version.effective_from)} />
            <Fact icon={Clock} label="Published" value={formatOptionalDate(version.published_at)} />
            <Fact icon={ShieldCheck} label="Owner" value={sop.owner_team || "Unassigned"} />
          </div>
        </div>
      </section>

      {sourceGroup ? (
        <section className="space-y-3" aria-label="Matched source from lookup">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Matched source</p>
              <h3 className="mt-1 text-base font-semibold leading-tight">Why this SOP opened from Lookup</h3>
            </div>
            {sourceQuery ? (
              <Button onClick={() => onSearchRelated(sourceQuery)} size="sm" type="button" variant="outline">
                <Search data-icon="inline-start" className="size-4" />
                Back to results
              </Button>
            ) : null}
          </div>
          <SourceContextCard
            autoScrollToHighlight
            group={sourceGroup}
            showDebugScore={debugEnabled}
          />
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(22rem,0.75fr)]">
        <div className="space-y-4">
          <PolicySection icon={ShieldCheck} title="Effective window">
            <dl className="grid gap-3 md:grid-cols-3">
              <Definition label="Status" value={version.status} />
              <Definition label="Effective from" value={formatOptionalDate(version.effective_from)} />
              <Definition label="Updated" value={formatDate(sop.updated_at)} />
            </dl>
          </PolicySection>

          <PolicySection icon={Checklist} title="Applicability">
            <p className="whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{sections.when_to_apply || "No applicability text was published for this SOP."}</p>
          </PolicySection>

          <PolicySection icon={GitBranch} title="Case reasons">
            {sop.case_reasons.length ? (
              <div className="grid gap-2">
                {sop.case_reasons.map((reason) => (
                  <div className="rounded-xl border bg-muted/25 px-3 py-2 text-sm" key={reason}>
                    {reason}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No case reason mapping was published.</p>
            )}
          </PolicySection>

          <PolicySection icon={FileText} title="Main procedure">
            <div className="space-y-4">
              {sections.input_requirements ? (
                <div>
                  <SectionTitle title="Input requirements" />
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{sections.input_requirements}</p>
                </div>
              ) : null}
              <div>
                <SectionTitle title="Handling checklist" />
                {sections.checklist.length ? (
                  <ol className="mt-3 grid gap-2">
                    {sections.checklist.map((step, index) => (
                      <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3" key={`${step}-${index}`}>
                        <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-sm font-semibold tabular-nums text-muted-foreground">
                          {index + 1}
                        </span>
                        <p className="min-w-0 rounded-xl border bg-muted/25 px-3 py-2 text-sm leading-6">{step}</p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">No checklist was published.</p>
                )}
              </div>
              {sections.agent_script ? (
                <div>
                  <SectionTitle title="Agent script" />
                  <p className="mt-2 whitespace-pre-wrap rounded-xl border bg-muted/25 p-3 text-sm leading-7">{sections.agent_script}</p>
                </div>
              ) : null}
            </div>
          </PolicySection>
        </div>

        <aside className="space-y-4">
          <PolicySection icon={Checklist} title="On this SOP">
            <nav className="grid gap-1 text-sm">
              {[
                "Effective window",
                "Applicability",
                "Case reasons",
                "Main procedure",
                "SLA",
                "Macro responses",
              ].map((item) => (
                <button
                  className="rounded-md px-2 py-1.5 text-left text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                  key={item}
                  onClick={() => document.getElementById(sectionId(item))?.scrollIntoView({ behavior: "smooth", block: "start" })}
                  type="button"
                >
                  {item}
                </button>
              ))}
            </nav>
          </PolicySection>

          <PolicySection icon={Clock} title="SLA">
            <p className="text-sm leading-6 text-muted-foreground">{sections.sla || "No explicit SLA was published."}</p>
          </PolicySection>

          <PolicySection icon={Copy} title="Macro responses">
            <div className="space-y-3">
              {sections.macro_response.map((macro) => (
                <div className="rounded-xl border bg-muted/25 p-3" key={macro.title}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h4 className="text-sm font-semibold">{macro.title}</h4>
                      <p className="mt-1 line-clamp-4 text-sm leading-6 text-muted-foreground">{macro.content}</p>
                    </div>
                    <MacroCopyButton macro={macro} onCopyMacro={onCopyMacro} />
                  </div>
                </div>
              ))}
              {!sections.macro_response.length ? (
                <p className="text-sm text-muted-foreground">No macro response was published.</p>
              ) : null}
              {copied ? (
                <div className="rounded-xl border bg-secondary px-3 py-2 text-sm text-secondary-foreground">Copied: {copied}</div>
              ) : null}
            </div>
          </PolicySection>

          <PolicySection icon={Folder} title="Category and related policies">
            <div className="space-y-2">
              <p className="text-xs leading-5 text-muted-foreground">
                Category is this SOP&apos;s topic facet for browse and search. Collections handle operational packages, ownership, tools, and governance.
              </p>
              <button
                className="flex w-full items-center justify-between gap-3 rounded-xl border bg-muted/25 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
                onClick={() => onOpenCategory(sop)}
                type="button"
              >
                <span className="min-w-0 truncate">Category: {sop.category || "Uncategorized"}</span>
                <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
              </button>
              {sections.related_policies?.map((policy) => (
                <button
                  className="flex w-full items-center justify-between gap-3 rounded-xl border bg-muted/25 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
                  key={policy}
                  onClick={() => onSearchRelated(policy)}
                  type="button"
                >
                  <span className="min-w-0 truncate">{policy}</span>
                  <Search className="size-4 shrink-0 text-muted-foreground" />
                </button>
              ))}
            </div>
          </PolicySection>

          <PolicySection icon={FileText} title={debugEnabled ? "Version snapshot" : "Review notes"}>
            <dl className="grid gap-3">
              <Definition label="Change summary" value={version.change_summary || "No change summary"} />
              <Definition label="Approved by" value={version.approved_by || "n/a"} />
              {debugEnabled ? (
                <>
                  <Definition label="Version ID" value={version.id} />
                  <Definition label="Current version pointer" value={sop.current_version_id} />
                </>
              ) : null}
            </dl>
          </PolicySection>
        </aside>
      </section>
    </div>
  );
}

function PolicySection({
  children,
  icon: Icon,
  title,
}: {
  children: ReactNode;
  icon: ElementType;
  title: string;
}) {
  return (
    <section className="scroll-mt-24 rounded-xl border bg-card p-4" id={sectionId(title)}>
      <div className="mb-3 flex items-center gap-2">
        <Icon className="size-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function sectionId(title: string) {
  return `sop-section-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")}`;
}

function Definition({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-muted/25 p-3">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words text-sm">{value}</dd>
    </div>
  );
}

function formatOptionalDate(value: string | undefined) {
  return value ? formatDate(value) : "n/a";
}

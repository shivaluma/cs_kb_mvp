import {
  Archive,
  Bot,
  Check,
  CheckCircle2,
  Clipboard,
  Copy,
  DatabaseZap,
  FileClock,
  History,
  Layers3,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";

type Macro = {
  title: string;
  content: string;
};

type SOP = {
  id: string;
  code: string;
  title: string;
  summary: string;
  audience: string[];
  vertical: string;
  category: string;
  tags: string[];
  case_reasons: string[];
  status: string;
  current_version_id: string;
  owner_team: string;
  updated_at: string;
  current_version: {
    id: string;
    version_number: number;
    status: string;
    change_summary: string;
    sections: {
      when_to_apply: string;
      input_requirements: string;
      checklist: string[];
      agent_script: string;
      macro_response: Macro[];
      sla?: string;
      escalation?: string;
      related_policies?: string[];
    };
  };
  analytics: {
    views: number;
    macro_copy: number;
    helpful: number;
    not_helpful: number;
  };
};

type SearchResult = {
  sop_id: string;
  title: string;
  snippet: string;
  category: string;
  audience: string[];
  vertical: string;
  tags: string[];
  updated_at: string;
  version: number;
  confidence: number;
};

type Homepage = {
  recently_updated: SOP[];
  most_viewed: SOP[];
  category_shortcuts: Array<{ key: string; label: string }>;
};

type AISuggestion = {
  answer: string;
  suggested_sops: Array<{
    sop_id: string;
    title: string;
    version: number;
    confidence: number;
  }>;
  citations: Array<{ sop_id: string; version_id: string; section: string }>;
  warnings: string[];
};

type FilterState = {
  audience: string;
  vertical: string;
  category: string;
};

const defaultFilters: FilterState = {
  audience: "all",
  vertical: "all",
  category: "all",
};

const filterOptions = {
  audience: ["customer", "driver", "merchant", "internal"],
  vertical: ["food", "payment", "safety", "delivery", "promotion"],
  category: ["case_handling", "verification", "escalation", "policy"],
};

const navItems = [
  { label: "Search", icon: Search, active: true },
  { label: "Review", icon: Clipboard },
  { label: "Analytics", icon: History },
  { label: "Archive", icon: Archive },
];

export function App() {
  const [homepage, setHomepage] = useState<Homepage | null>(null);
  const [query, setQuery] = useState("khong nhan du mon");
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SOP | null>(null);
  const [aiSuggestion, setAiSuggestion] = useState<AISuggestion | null>(null);
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  const [copyError, setCopyError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadHomepage() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/homepage`);
        if (!response.ok) {
          throw new Error("Homepage request failed");
        }
        const data = (await response.json()) as Homepage;
        if (!active) {
          return;
        }
        setHomepage(data);
        setSelected(data.recently_updated[0] ?? null);
      } catch {
        if (active) {
          setError(
            "Cannot reach the SOP API. Check that cs-kb-api is running on port 8080.",
          );
        }
      } finally {
        if (active) {
          setBooting(false);
        }
      }
    }

    loadHomepage();
    runSearch(query, filters);

    return () => {
      active = false;
    };
  }, []);

  const listSource = useMemo(() => {
    if (results.length > 0) {
      return results;
    }
    return homepage?.most_viewed.map(toSearchResult) ?? [];
  }, [homepage, results]);

  async function runSearch(nextQuery = query, nextFilters = filters) {
    setLoading(true);
    setError("");
    setAiSuggestion(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: nextQuery,
          include_semantic: true,
          filters: compactFilters(nextFilters),
        }),
      });

      if (!response.ok) {
        throw new Error("Search request failed");
      }

      const data = await response.json();
      setResults(data.results ?? []);
    } catch {
      setResults([]);
      setError(
        "Search failed. Keyword SOP lookup should stay available even when AI is down.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function openSOP(id: string) {
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/sops/${id}`);
      if (!response.ok) {
        throw new Error("SOP request failed");
      }
      setSelected(await response.json());
      setAiSuggestion(null);
    } catch {
      setError("Cannot open this SOP. It may be archived or unavailable.");
    }
  }

  async function askAI() {
    if (!selected) {
      return;
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/ai/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, sop_id: selected.id }),
    });
    setAiSuggestion(await response.json());
  }

  async function copyMacro(macro: Macro) {
    setCopied("");
    setCopyError("");

    try {
      await navigator.clipboard.writeText(macro.content);
      setCopied(macro.title);
      window.setTimeout(() => setCopied(""), 1800);
    } catch {
      setCopyError(
        `Clipboard permission blocked. Macro selected: ${macro.title}`,
      );
      window.setTimeout(() => setCopyError(""), 2600);
    }
  }

  function updateFilter(key: keyof FilterState, value: string) {
    const nextFilters = { ...filters, [key]: value };
    setFilters(nextFilters);
    runSearch(query, nextFilters);
  }

  const selectedVersion = selected?.current_version;
  const feedbackTotal = selected
    ? selected.analytics.helpful + selected.analytics.not_helpful
    : 0;
  const helpfulRate =
    feedbackTotal && selected
      ? Math.round((selected.analytics.helpful / feedbackTotal) * 100)
      : 0;

  return (
    <main className="min-h-svh bg-background text-foreground dark">
      <a
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        href="#main-content"
      >
        Skip to main content
      </a>

      <div className="grid min-h-svh lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="border-b bg-sidebar/80 px-4 py-4 lg:border-b-0 lg:border-r lg:px-5">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <ShieldCheck className="size-5" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">CS SOP KB</p>
              <p className="truncate text-xs text-muted-foreground">
                Approved knowledge
              </p>
            </div>
          </div>

          <nav
            aria-label="Main navigation"
            className="mt-5 grid grid-cols-2 gap-2 lg:grid-cols-1"
          >
            {navItems.map((item) => (
              <Button
                className={cn(
                  "justify-start",
                  item.active &&
                  "bg-sidebar-accent text-sidebar-accent-foreground",
                )}
                key={item.label}
                type="button"
                variant={item.active ? "secondary" : "ghost"}
              >
                <item.icon data-icon="inline-start" className="size-4" />
                {item.label}
              </Button>
            ))}
          </nav>

          <Separator className="my-5 hidden lg:block" />

          <section className="hidden lg:block">
            <div className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
              <Layers3 className="size-3.5" />
              Shortcuts
            </div>
            <div className="grid gap-2">
              {homepage?.category_shortcuts.map((item) => (
                <Button
                  className="justify-between"
                  key={item.key}
                  onClick={() => updateFilter("category", item.key)}
                  type="button"
                  variant="outline"
                >
                  {item.label}
                  <Badge variant="secondary">{item.key.split("_")[0]}</Badge>
                </Button>
              ))}
            </div>
          </section>

          <section className="mt-5 hidden rounded-xl border bg-card p-3 text-sm lg:block">
            <div className="flex items-center gap-2 font-medium">
              <DatabaseZap className="size-4 text-primary" />
              Source rules
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              Agents see only latest published SOP versions. AI suggestions must
              cite source sections.
            </p>
          </section>
        </aside>

        <section className="min-w-0" id="main-content">
          <header className="border-b bg-background/95 px-4 py-4 supports-[backdrop-filter]:bg-background/80 md:px-6 lg:sticky lg:top-0 lg:z-20 lg:backdrop-blur">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="min-w-0">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <Badge variant="outline">
                    <CheckCircle2 data-icon="inline-start" className="size-3" />
                    Latest published only
                  </Badge>
                  <Badge
                    className="bg-info text-info-foreground"
                    variant="secondary"
                  >
                    Agent view
                  </Badge>
                </div>
                <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                  Search approved CS procedures
                </h1>
                <p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">
                  Fast lookup for SOPs, macro copy, escalation rules, and
                  grounded AI suggestions.
                </p>
              </div>

              <div className="grid grid-cols-3 gap-2 text-right md:min-w-72">
                <Metric
                  label="SOPs"
                  value={homepage?.most_viewed.length ?? 0}
                />
                <Metric label="Views" value={sumViews(homepage?.most_viewed)} />
                <Metric label="AI mode" value="P1" />
              </div>
            </div>
          </header>

          <div className="grid gap-4 p-4 md:p-6 xl:grid-cols-[minmax(22rem,0.78fr)_minmax(34rem,1.22fr)]">
            <section className="min-w-0 space-y-4">
              <Card className="rounded-2xl">
                <CardHeader className="pb-0">
                  <CardTitle>Lookup queue</CardTitle>
                  <CardDescription>
                    Keyword first, semantic contract enabled, filters stay
                    explicit.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 pt-1">
                  <div className="grid gap-2">
                    <label
                      className="text-xs font-medium text-muted-foreground"
                      htmlFor="sop-search"
                    >
                      Search query
                    </label>
                    <div className="flex gap-2">
                      <div className="relative min-w-0 flex-1">
                        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          className="pl-8"
                          id="sop-search"
                          onChange={(event) => setQuery(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              runSearch();
                            }
                          }}
                          placeholder="khong nhan du mon, CR_FOOD_MISSING_ITEM..."
                          value={query}
                        />
                      </div>
                      <Button
                        disabled={loading}
                        onClick={() => runSearch()}
                        type="button"
                      >
                        {loading ? (
                          <Loader2
                            data-icon="inline-start"
                            className="size-4 animate-spin"
                          />
                        ) : null}
                        Search
                      </Button>
                    </div>
                  </div>

                  <div className="grid gap-2 sm:grid-cols-3">
                    {Object.entries(filterOptions).map(([key, options]) => (
                      <FilterSelect
                        key={key}
                        label={key}
                        onValueChange={(value) =>
                          updateFilter(key as keyof FilterState, value)
                        }
                        options={options}
                        value={filters[key as keyof FilterState]}
                      />
                    ))}
                  </div>

                  {error ? (
                    <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {error}
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              <Card className="rounded-2xl">
                <CardHeader className="pb-1">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle>
                        {results.length > 0
                          ? "Search results"
                          : "Most viewed SOPs"}
                      </CardTitle>
                      <CardDescription>
                        {loading
                          ? "Searching published index"
                          : `${listSource.length} visible items`}
                      </CardDescription>
                    </div>
                    <Badge variant="outline">semantic-ready</Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-[31rem] pr-3">
                    <div className="space-y-2">
                      {loading || booting ? (
                        <ResultSkeleton />
                      ) : listSource.length === 0 ? (
                        <EmptyResults query={query} />
                      ) : (
                        listSource.map((item) => (
                          <ResultButton
                            item={item}
                            key={item.sop_id}
                            onClick={() => openSOP(item.sop_id)}
                            selected={selected?.id === item.sop_id}
                          />
                        ))
                      )}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>
            </section>

            <article className="min-w-0">
              {selected && selectedVersion ? (
                <Card className="rounded-2xl">
                  <CardHeader className="space-y-4">
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div className="min-w-0">
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <Badge variant="secondary">{selected.code}</Badge>
                          <Badge variant="outline">
                            v{selectedVersion.version_number}
                          </Badge>
                          <Badge
                            className="bg-success text-success-foreground"
                            variant="secondary"
                          >
                            published
                          </Badge>
                        </div>
                        <CardTitle className="text-xl md:text-2xl">
                          {selected.title}
                        </CardTitle>
                        <CardDescription className="mt-2 max-w-[72ch] text-sm leading-6">
                          {selected.summary}
                        </CardDescription>
                      </div>

                      <Button onClick={askAI} type="button" variant="outline">
                        <Sparkles
                          data-icon="inline-start"
                          className="size-4 text-warning"
                        />
                        Ask AI
                      </Button>
                    </div>

                    <div className="grid gap-2 sm:grid-cols-3">
                      <Fact
                        icon={FileClock}
                        label="Updated"
                        value={formatDate(selected.updated_at)}
                      />
                      <Fact
                        icon={ShieldCheck}
                        label="Owner"
                        value={selected.owner_team}
                      />
                      <Fact
                        icon={Check}
                        label="Helpful"
                        value={`${helpfulRate || 0}%`}
                      />
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-5">
                    <Tabs defaultValue="procedure">
                      <TabsList className="grid w-full grid-cols-3">
                        <TabsTrigger value="procedure">Procedure</TabsTrigger>
                        <TabsTrigger value="macros">Macros</TabsTrigger>
                        <TabsTrigger value="governance">Governance</TabsTrigger>
                      </TabsList>

                      <TabsContent className="mt-5 space-y-5" value="procedure">
                        <TextBlock
                          title="When to apply"
                          value={selectedVersion.sections.when_to_apply}
                        />
                        <TextBlock
                          title="Input requirements"
                          value={selectedVersion.sections.input_requirements}
                        />

                        <section>
                          <SectionTitle title="Handling checklist" />
                          <ol className="mt-3 grid gap-2">
                            {selectedVersion.sections.checklist.map(
                              (step, index) => (
                                <li
                                  className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3"
                                  key={step}
                                >
                                  <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-sm font-semibold text-primary">
                                    {index + 1}
                                  </span>
                                  <p className="min-w-0 rounded-xl border bg-muted/35 px-3 py-2 text-sm leading-6">
                                    {step}
                                  </p>
                                </li>
                              ),
                            )}
                          </ol>
                        </section>

                        <div className="grid gap-3 md:grid-cols-2">
                          <TextBlock
                            title="SLA"
                            value={
                              selectedVersion.sections.sla ??
                              "No SLA configured."
                            }
                          />
                          <TextBlock
                            title="Escalation"
                            value={
                              selectedVersion.sections.escalation ??
                              "No escalation configured."
                            }
                          />
                        </div>
                      </TabsContent>

                      <TabsContent className="mt-5 space-y-3" value="macros">
                        {selectedVersion.sections.macro_response.map(
                          (macro) => (
                            <div
                              className="rounded-xl border bg-muted/25 p-3"
                              key={macro.title}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <h3 className="text-sm font-semibold">
                                    {macro.title}
                                  </h3>
                                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                    {macro.content}
                                  </p>
                                </div>
                                <Button
                                  aria-label={`Copy macro ${macro.title}`}
                                  onClick={() => copyMacro(macro)}
                                  size="icon"
                                  type="button"
                                  variant="outline"
                                >
                                  <Copy className="size-4" />
                                </Button>
                              </div>
                            </div>
                          ),
                        )}
                        {copied ? (
                          <div className="rounded-xl border border-success/25 bg-success/10 px-3 py-2 text-sm text-success">
                            Copied: {copied}
                          </div>
                        ) : null}
                        {copyError ? (
                          <div className="rounded-xl border border-warning/25 bg-warning/10 px-3 py-2 text-sm text-warning">
                            {copyError}
                          </div>
                        ) : null}
                      </TabsContent>

                      <TabsContent
                        className="mt-5 space-y-4"
                        value="governance"
                      >
                        <div className="grid gap-3 md:grid-cols-2">
                          <GovernanceItem
                            label="Change summary"
                            value={selectedVersion.change_summary}
                          />
                          <GovernanceItem
                            label="Version ID"
                            value={selectedVersion.id}
                          />
                          <GovernanceItem
                            label="Current version pointer"
                            value={selected.current_version_id}
                          />
                          <GovernanceItem
                            label="Case reasons"
                            value={selected.case_reasons.join(", ")}
                          />
                        </div>

                        <div className="flex flex-wrap gap-2">
                          {selected.tags.map((tag) => (
                            <Badge key={tag} variant="outline">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </TabsContent>
                    </Tabs>

                    {aiSuggestion ? (
                      <AISuggestionPanel suggestion={aiSuggestion} />
                    ) : null}

                    <Separator />

                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-sm text-muted-foreground">
                        Agent script:{" "}
                        <span className="text-foreground">
                          {selectedVersion.sections.agent_script}
                        </span>
                      </p>
                      <div className="flex gap-2">
                        <Button type="button" variant="outline">
                          <ThumbsUp
                            data-icon="inline-start"
                            className="size-4"
                          />
                          Helpful
                        </Button>
                        <Button type="button" variant="outline">
                          <ThumbsDown
                            data-icon="inline-start"
                            className="size-4"
                          />
                          Not useful
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card className="grid min-h-[40rem] place-items-center rounded-2xl">
                  <CardContent className="max-w-sm text-center">
                    <Search className="mx-auto size-9 text-muted-foreground" />
                    <h2 className="mt-3 text-base font-semibold">
                      Select a SOP
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Search or choose a popular SOP to inspect latest published
                      content.
                    </p>
                  </CardContent>
                </Card>
              )}
            </article>
          </div>
        </section>
      </div>
    </main>
  );
}

function FilterSelect({
  label,
  onValueChange,
  options,
  value,
}: {
  label: string;
  onValueChange: (value: string) => void;
  options: string[];
  value: string;
}) {
  return (
    <div className="grid gap-1.5">
      <label className="text-xs font-medium capitalize text-muted-foreground">
        {label}
      </label>
      <Select onValueChange={onValueChange} value={value}>
        <SelectTrigger className="w-full" size="default">
          <SelectValue placeholder={label} />
        </SelectTrigger>
        <SelectContent align="start">
          <SelectItem value="all">All {label}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function ResultButton({
  item,
  onClick,
  selected,
}: {
  item: SearchResult;
  onClick: () => void;
  selected: boolean;
}) {
  return (
    <button
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        selected && "border-primary bg-primary/5",
      )}
      onClick={onClick}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-sm font-semibold leading-5">
          {item.title}
        </h3>
        <Badge variant="secondary">v{item.version}</Badge>
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-5 text-muted-foreground">
        {item.snippet}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{item.category}</Badge>
        <Badge variant="outline">{item.vertical}</Badge>
        <span className="text-xs text-muted-foreground">
          {formatDate(item.updated_at)}
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${Math.max(item.confidence * 100, 8)}%` }}
        />
      </div>
    </button>
  );
}

function AISuggestionPanel({ suggestion }: { suggestion: AISuggestion }) {
  return (
    <section className="rounded-2xl border border-warning/25 bg-warning/10 p-4">
      <div className="flex items-center gap-2">
        <Bot className="size-4 text-warning" />
        <h3 className="text-sm font-semibold">Grounded AI suggestion</h3>
      </div>
      <p className="mt-2 text-sm leading-6">{suggestion.answer}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {(suggestion.citations ?? []).map((citation) => (
          <Badge
            key={`${citation.version_id}-${citation.section}`}
            variant="outline"
          >
            {citation.sop_id} / {citation.section}
          </Badge>
        ))}
        {(suggestion.warnings ?? []).map((warning) => (
          <Badge
            className="border-warning/30 text-warning"
            key={warning}
            variant="outline"
          >
            {warning}
          </Badge>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border bg-card px-3 py-2">
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function Fact({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileClock;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border bg-muted/25 p-3">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Icon className="size-3.5" />
        {label}
      </div>
      <p className="mt-1 truncate text-sm font-semibold">{value}</p>
    </div>
  );
}

function TextBlock({ title, value }: { title: string; value: string }) {
  return (
    <section>
      <SectionTitle title={title} />
      <p className="mt-2 rounded-xl border bg-muted/25 px-3 py-2 text-sm leading-6 text-muted-foreground">
        {value}
      </p>
    </section>
  );
}

function SectionTitle({ title }: { title: string }) {
  return <h3 className="text-sm font-semibold">{title}</h3>;
}

function GovernanceItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-muted/25 p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm">{value}</p>
    </div>
  );
}

function EmptyResults({ query }: { query: string }) {
  return (
    <div className="rounded-xl border border-dashed p-6 text-center">
      <Search className="mx-auto size-8 text-muted-foreground" />
      <h3 className="mt-3 text-sm font-semibold">No published SOP matched</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Try a tag, CRM case reason, or a shorter phrase for{" "}
        <span className="font-medium text-foreground">{query}</span>.
      </p>
    </div>
  );
}

function ResultSkeleton() {
  return (
    <>
      {[0, 1, 2].map((item) => (
        <div className="rounded-xl border p-3" key={item}>
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-2/3" />
          <div className="mt-4 flex gap-2">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
        </div>
      ))}
    </>
  );
}

function toSearchResult(sop: SOP): SearchResult {
  return {
    sop_id: sop.id,
    title: sop.title,
    snippet: sop.summary,
    category: sop.category,
    audience: sop.audience,
    vertical: sop.vertical,
    tags: sop.tags,
    updated_at: sop.updated_at,
    version: sop.current_version.version_number,
    confidence: 0.8,
  };
}

function compactFilters(filters: FilterState) {
  return {
    audience: filters.audience === "all" ? [] : [filters.audience],
    vertical: filters.vertical === "all" ? [] : [filters.vertical],
    category: filters.category === "all" ? [] : [filters.category],
  };
}

function sumViews(sops?: SOP[]) {
  return sops?.reduce((sum, sop) => sum + sop.analytics.views, 0) ?? 0;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

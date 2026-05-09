import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  defaultFilters,
  defaultSynonymDraft,
  defaultUpload,
  type Workspace,
} from "@/constants";
import {
  useAcceptSuggestion,
  useArchiveDocument,
  useAISuggest,
  useCreateSynonym,
  useDocumentChunks,
  useDocuments,
  useDocumentVersions,
  useExtractionUnits,
  useGenerateSuggestions,
  useHomepage,
  usePublishVersion,
  useRetrieval,
  useSearch,
  useSOP,
  useSyncSynonyms,
  useSynonyms,
  useSynonymSuggestions,
  useTransitionSynonym,
  useUploadDocument,
  useUpdateExtractionUnit,
} from "@/hooks/use-kb-api";
import { compactFilters, fileExternalId, splitList, toSearchResult } from "@/lib/format";
import type {
  AISuggestion,
  DocumentSummary,
  ExtractionUnit,
  ExtractionUnitUpdate,
  FilterState,
  Macro,
  RetrievalResponse,
  RetrievalResult,
  SOP,
  SynonymDraft,
  SynonymGroup,
  SynonymSuggestion,
  UploadState,
} from "@/types";
import { DashboardWorkspace } from "@/workspaces/dashboard-workspace";
import { DocumentsWorkspace } from "@/workspaces/documents-workspace";
import { LookupWorkspace } from "@/workspaces/lookup-workspace";
import { RetrievalWorkspace } from "@/workspaces/retrieval-workspace";
import { SynonymsWorkspace } from "@/workspaces/synonyms-workspace";

export function App() {
  const [workspace, setWorkspace] = useState<Workspace>("dashboard");
  const [query, setQuery] = useState("khach khong nhan du mon co duoc refund khong");
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [retrievalMode, setRetrievalMode] = useState<RetrievalResponse["mode"]>("hybrid");
  const [selected, setSelected] = useState<SOP | null>(null);
  const [selectedDocumentMatch, setSelectedDocumentMatch] = useState<RetrievalResult | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<DocumentSummary | null>(null);
  const [selectedChunkVersionId, setSelectedChunkVersionId] = useState("");
  const [synonymStatus, setSynonymStatus] = useState("active");
  const [upload, setUpload] = useState<UploadState>(defaultUpload);
  const [synonymDraft, setSynonymDraft] = useState<SynonymDraft>(defaultSynonymDraft);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  const [copyError, setCopyError] = useState("");

  const homepageQuery = useHomepage();
  const documentsQuery = useDocuments();
  const versionsQuery = useDocumentVersions(selectedDocument?.document_id);
  const chunksQuery = useDocumentChunks(selectedDocument?.document_id, selectedChunkVersionId);
  const extractionUnitsQuery = useExtractionUnits(selectedDocument?.document_id, selectedChunkVersionId);
  const synonymsQuery = useSynonyms(synonymStatus);
  const suggestionsQuery = useSynonymSuggestions();
  const searchMutation = useSearch();
  const sopMutation = useSOP();
  const aiSuggestMutation = useAISuggest();
  const retrievalMutation = useRetrieval();
  const uploadMutation = useUploadDocument();
  const publishMutation = usePublishVersion();
  const updateExtractionUnitMutation = useUpdateExtractionUnit();
  const archiveDocumentMutation = useArchiveDocument();
  const createSynonymMutation = useCreateSynonym();
  const transitionSynonymMutation = useTransitionSynonym();
  const syncSynonymsMutation = useSyncSynonyms();
  const generateSuggestionsMutation = useGenerateSuggestions();
  const acceptSuggestionMutation = useAcceptSuggestion();

  const homepage = homepageQuery.data;
  const documents = useMemo(
    () =>
      [...(documentsQuery.data ?? [])].sort((left, right) => {
        if (left.status !== right.status) {
          return left.status === "active" ? -1 : 1;
        }
        return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      }),
    [documentsQuery.data],
  );
  const versions = versionsQuery.data ?? [];
  const chunks = chunksQuery.data ?? [];
  const extractionUnits = extractionUnitsQuery.data ?? [];
  const synonyms = synonymsQuery.data ?? [];
  const suggestions = suggestionsQuery.data ?? [];
  const searchResults = searchMutation.data?.results ?? [];
  const semanticResults = searchMutation.data?.semantic_results ?? [];
  const retrieval = retrievalMutation.data ?? null;
  const aiSuggestion = (aiSuggestMutation.data as AISuggestion | undefined) ?? null;

  useEffect(() => {
    if (!selected && homepage?.recently_updated[0]) {
      setSelected(homepage.recently_updated[0]);
    }
  }, [homepage, selected]);

  useEffect(() => {
    const firstActiveDocument = documents.find((document) => document.status === "active") ?? documents[0];
    if (!selectedDocument && firstActiveDocument) {
      setSelectedDocument(firstActiveDocument);
      setSelectedChunkVersionId(firstActiveDocument.latest_version_id ?? "");
    }
  }, [documents, selectedDocument]);

  useEffect(() => {
    if (selectedDocument?.latest_version_id && !selectedChunkVersionId) {
      setSelectedChunkVersionId(selectedDocument.latest_version_id);
    }
  }, [selectedDocument, selectedChunkVersionId]);

  useEffect(() => {
    runSearch();
    runRetrieval();
  }, []);

  const listSource = useMemo(() => {
    if (searchResults.length > 0) {
      return searchResults;
    }
    return homepage?.most_viewed.map(toSearchResult) ?? [];
  }, [homepage, searchResults]);

  const feedbackTotal = selected
    ? selected.analytics.helpful + selected.analytics.not_helpful
    : 0;
  const helpfulRate =
    feedbackTotal && selected
      ? Math.round((selected.analytics.helpful / feedbackTotal) * 100)
      : 0;

  function reportError(message: string) {
    setError(message);
    setNotice("");
  }

  function reportNotice(message: string) {
    setNotice(message);
    setError("");
  }

  function runSearch(nextQuery = query, nextFilters = filters) {
    searchMutation.mutate(
      {
        query: nextQuery,
        include_semantic: true,
        filters: compactFilters(nextFilters),
      },
      {
        onError: () =>
          reportError("Search failed. Keyword SOP lookup should stay available even when AI is down."),
      },
    );
  }

  function runRetrieval(nextQuery = query, mode = retrievalMode) {
    retrievalMutation.mutate(
      {
        query: nextQuery,
        mode,
        limit: 6,
        filters: {
          ...compactFilters(filters),
          status: ["published"],
        },
      },
      {
        onError: () => reportError("Retrieval failed. Check cs-kb-ai and Postgres/pgvector."),
      },
    );
  }

  function openSOP(id: string) {
    sopMutation.mutate(id, {
      onSuccess: (sop) => {
        setSelected(sop);
        setSelectedDocumentMatch(null);
        setWorkspace("lookup");
      },
      onError: () => reportError("Cannot open this SOP. It may be archived or unavailable."),
    });
  }

  function askAI() {
    if (!selected) {
      return;
    }
    aiSuggestMutation.mutate(
      { query, sop_id: selected.id },
      { onError: () => reportError("AI suggestion failed.") },
    );
  }

  async function copyMacro(macro: Macro) {
    setCopied("");
    setCopyError("");
    try {
      await navigator.clipboard.writeText(macro.content);
      setCopied(macro.title);
      window.setTimeout(() => setCopied(""), 1800);
    } catch {
      setCopyError(`Clipboard permission blocked. Macro selected: ${macro.title}`);
      window.setTimeout(() => setCopyError(""), 2600);
    }
  }

  function updateFilter(key: keyof FilterState, value: string) {
    const nextFilters = { ...filters, [key]: value };
    setFilters(nextFilters);
    runSearch(query, nextFilters);
  }

  function handleUpload() {
    if (!upload.file) {
      reportError("Choose a TXT, MD, PDF, DOCX, Excel, or image file before uploading.");
      return;
    }
    const maxBytes = 15 * 1024 * 1024;
    const allowedExtensions = [".txt", ".md", ".markdown", ".pdf", ".docx", ".xlsx", ".xlsm", ".xls", ".png", ".jpg", ".jpeg", ".webp"];
    const lowerName = upload.file.name.toLowerCase();
    const validType = allowedExtensions.some((extension) => lowerName.endsWith(extension));
    if (!validType) {
      reportError("Unsupported file type. Use TXT, MD, PDF, DOCX, Excel, PNG, JPG, or WebP.");
      return;
    }
    if (upload.file.size > maxBytes) {
      reportError("File is too large for the demo pipeline. Keep uploads under 15MB.");
      return;
    }

    const form = new FormData();
    form.append("file", upload.file);
    form.append("external_id", upload.externalId || fileExternalId(upload.file.name));
    form.append("title", upload.title || upload.file.name);
    form.append("status", upload.status);
    form.append("created_by", "cs-ops-ui");
    form.append("change_summary", "Uploaded from CS KB web console");
    form.append(
      "metadata",
      JSON.stringify({
        audience: [upload.audience],
        vertical: upload.vertical,
        category: upload.category,
        tags: splitList(upload.tags),
        case_reasons: splitList(upload.caseReasons),
        owner_team: upload.ownerTeam,
        source: "web_upload",
      }),
    );

    uploadMutation.mutate(form, {
      onSuccess: (data) => {
        reportNotice(`Uploaded ${data.title} v${data.version_number}, ${data.chunk_count} chunks extracted for review.`);
        setSelectedChunkVersionId("");
        setUpload((current) => ({ ...current, file: null, title: "", externalId: "" }));
        setWorkspace("documents");
      },
      onError: () => reportError("Upload failed. Confirm file type, size, and AI service health."),
    });
  }

  function publishVersion(versionId: string) {
    const selectedVersionUnits = selectedChunkVersionId === versionId ? extractionUnits : [];
    const pendingReviewCount = selectedVersionUnits.filter((unit) => unit.review_status === "needs_review").length;
    const confirmed = window.confirm(
      pendingReviewCount > 0
        ? `This version still has ${pendingReviewCount} units marked needs_review. Publish anyway and lock this version?`
        : "Publish this reviewed version and archive the previous published version?",
    );
    if (!confirmed) {
      return;
    }
    publishMutation.mutate(
      { versionId, actor: "cs-lead-ui" },
      {
        onSuccess: () => {
          setSelectedChunkVersionId(versionId);
          reportNotice("Version published. Previous published version was archived and Meilisearch was updated.");
        },
      },
    );
  }

  function updateExtractionUnit(unit: ExtractionUnit, update: ExtractionUnitUpdate) {
    updateExtractionUnitMutation.mutate(
      { unitId: unit.unit_id, update },
      {
        onSuccess: () => reportNotice(`Saved extraction unit ${unit.unit_index}. Retrieval embedding was refreshed.`),
        onError: () => reportError("Could not save this extraction unit. Published versions are immutable."),
      },
    );
  }

  function archiveDocument(document: DocumentSummary) {
    const confirmed = window.confirm(`Archive "${document.title}"? It will be removed from active retrieval and Meilisearch.`);
    if (!confirmed) {
      return;
    }
    archiveDocumentMutation.mutate(
      { documentId: document.document_id, actor: "cs-ops-ui" },
      {
        onSuccess: () => {
          reportNotice(`Archived ${document.title}.`);
          setSelectedDocument(null);
          setSelectedChunkVersionId("");
        },
        onError: () => reportError("Archive failed. Check AI service and document state."),
      },
    );
  }

  function createSynonymGroup() {
    createSynonymMutation.mutate(
      {
        canonical_key: synonymDraft.canonicalKey,
        synonym_type: synonymDraft.synonymType,
        domain: synonymDraft.domain,
        audience: synonymDraft.audience,
        status: synonymDraft.status,
        created_by: "cs-ops-ui",
        terms: splitList(synonymDraft.terms),
      },
      {
        onSuccess: (group) => {
          reportNotice(`Created synonym group ${group.canonical_key}.`);
          setSynonymStatus(group.status);
        },
        onError: () => reportError("Could not create synonym group. Check required fields."),
      },
    );
  }

  function transitionSynonym(group: SynonymGroup, action: "submit-review" | "approve" | "archive") {
    const actor = action === "approve" ? "cs-lead-ui" : "cs-ops-ui";
    transitionSynonymMutation.mutate(
      { groupId: group.id, action, actor },
      { onSuccess: () => reportNotice(`Synonym ${action} completed for ${group.canonical_key}.`) },
    );
  }

  function syncSynonyms() {
    syncSynonymsMutation.mutate(undefined, {
      onSuccess: (data) => reportNotice(`Synced ${data.synonym_count} synonym keys to Meilisearch.`),
      onError: () => reportError("Meilisearch synonym sync failed."),
    });
  }

  function generateSuggestions() {
    generateSuggestionsMutation.mutate(undefined, {
      onSuccess: (data) => reportNotice(`Generated ${data.length} new suggestion candidates.`),
    });
  }

  function acceptSuggestion(suggestion: SynonymSuggestion) {
    const canonical = suggestion.canonical_key || synonymDraft.canonicalKey || "manual_review";
    acceptSuggestionMutation.mutate(
      {
        suggestionId: suggestion.id,
        canonical_key: canonical,
        synonym_type: "one_way",
        actor: "cs-ops-ui",
        submit_review: true,
      },
      { onSuccess: () => reportNotice(`Accepted suggestion into review as ${canonical}.`) },
    );
  }

  const busyKey =
    uploadMutation.isPending ? "upload" :
    archiveDocumentMutation.isPending ? "archive-document" :
    createSynonymMutation.isPending ? "create-synonym" :
    syncSynonymsMutation.isPending ? "sync-synonyms" :
    generateSuggestionsMutation.isPending ? "generate-suggestions" :
    "";

  return (
    <AppShell
      documentCount={documents.length}
      error={error || (homepageQuery.error ? "Cannot reach the API. Check Docker Compose and port 8080." : "")}
      latency={retrieval ? `${retrieval.latency_ms}ms` : "n/a"}
      notice={notice}
      onDismissError={() => setError("")}
      onDismissNotice={() => setNotice("")}
      onWorkspaceChange={setWorkspace}
      synonymCount={synonyms.length}
      workspace={workspace}
    >
      {workspace === "dashboard" ? (
        <DashboardWorkspace
          documents={documents}
          homepage={homepage}
          onRunSearch={() => runSearch()}
          onWorkspaceChange={setWorkspace}
          query={query}
          setQuery={setQuery}
          synonyms={synonyms}
        />
      ) : null}

      {workspace === "lookup" ? (
        <LookupWorkspace
          aiSuggestion={aiSuggestion}
          booting={homepageQuery.isLoading}
          copied={copied}
          copyError={copyError}
          feedbackRate={helpfulRate}
          filters={filters}
          listSource={listSource}
          loading={searchMutation.isPending}
          onAskAI={askAI}
          onCopyMacro={copyMacro}
          onSelectDocumentMatch={(match) => {
            setSelectedDocumentMatch(match);
            setSelected(null);
          }}
          onOpenSOP={openSOP}
          onRunSearch={() => runSearch()}
          onUpdateFilter={updateFilter}
          query={query}
          selected={selected}
          selectedDocumentMatch={selectedDocumentMatch}
          selectedVersion={selected?.current_version}
          semanticResults={semanticResults}
          setQuery={setQuery}
        />
      ) : null}

      {workspace === "retrieval" ? (
        <RetrievalWorkspace
          busy={retrievalMutation.isPending}
          filters={filters}
          mode={retrievalMode}
          onModeChange={setRetrievalMode}
          onRetrieve={() => runRetrieval()}
          onUpdateFilter={updateFilter}
          query={query}
          retrieval={retrieval}
          setQuery={setQuery}
        />
      ) : null}

      {workspace === "documents" ? (
        <DocumentsWorkspace
          busyKey={busyKey || (publishMutation.isPending ? "publishing" : "")}
          chunks={chunks}
          chunksLoading={chunksQuery.isFetching}
          documents={documents}
          extractionUnits={extractionUnits}
          extractionUnitsLoading={extractionUnitsQuery.isFetching}
          onArchiveDocument={archiveDocument}
          onInspectVersion={setSelectedChunkVersionId}
          onPublishVersion={publishVersion}
          onRefreshDocuments={() => documentsQuery.refetch()}
          onSelectDocument={(documentId) => {
            const document = documents.find((item) => item.document_id === documentId);
            if (document) {
              setSelectedDocument(document);
              setSelectedChunkVersionId(document.latest_version_id ?? "");
            }
          }}
          onUpdateExtractionUnit={updateExtractionUnit}
          onUpload={handleUpload}
          savingUnitId={updateExtractionUnitMutation.variables?.unitId ?? ""}
          selectedDocument={selectedDocument}
          selectedChunkVersionId={selectedChunkVersionId}
          setSelectedDocument={setSelectedDocument}
          setUpload={setUpload}
          upload={upload}
          versions={versions}
        />
      ) : null}

      {workspace === "synonyms" ? (
        <SynonymsWorkspace
          busyKey={busyKey}
          draft={synonymDraft}
          onAcceptSuggestion={acceptSuggestion}
          onCreate={createSynonymGroup}
          onGenerateSuggestions={generateSuggestions}
          onRefreshSuggestions={() => suggestionsQuery.refetch()}
          onRefreshSynonyms={() => synonymsQuery.refetch()}
          onSetStatus={(status) => setSynonymStatus(status === "all" ? "" : status)}
          onSync={syncSynonyms}
          onTransition={transitionSynonym}
          setDraft={setSynonymDraft}
          status={synonymStatus}
          suggestions={suggestions}
          synonyms={synonyms}
        />
      ) : null}
    </AppShell>
  );
}

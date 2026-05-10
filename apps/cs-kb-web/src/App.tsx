import { useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useNavigate, useRouterState } from "@tanstack/react-router";

import { KbAppProvider } from "@/app-context";
import { AppShell } from "@/components/app-shell";
import {
  defaultFilters,
  defaultSynonymDraft,
  defaultUpload,
  pathForWorkspace,
  type Workspace,
  workspaceFromPath,
} from "@/constants";
import {
  useAcceptSuggestion,
  useArchiveDocument,
  useAISuggest,
  useBulkReviewVersion,
  useCreateSynonym,
  useDocumentChunks,
  useDocumentMetadataPreview,
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
  useVersionRawText,
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

export function App() {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const workspace = workspaceFromPath(pathname);
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
  const autoSelectedInitialSop = useRef(false);

  const homepageQuery = useHomepage();
  const documentsQuery = useDocuments();
  const versionsQuery = useDocumentVersions(selectedDocument?.document_id);
  const chunksQuery = useDocumentChunks(selectedDocument?.document_id, selectedChunkVersionId);
  const extractionUnitsQuery = useExtractionUnits(selectedDocument?.document_id, selectedChunkVersionId);
  const versionRawQuery = useVersionRawText(selectedChunkVersionId);
  const synonymsQuery = useSynonyms(synonymStatus);
  const suggestionsQuery = useSynonymSuggestions();
  const searchMutation = useSearch();
  const sopMutation = useSOP();
  const aiSuggestMutation = useAISuggest();
  const retrievalMutation = useRetrieval();
  const uploadMutation = useUploadDocument();
  const metadataPreviewMutation = useDocumentMetadataPreview();
  const publishMutation = usePublishVersion();
  const bulkReviewMutation = useBulkReviewVersion();
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
    if (!autoSelectedInitialSop.current && !selected && homepage?.recently_updated?.[0]) {
      autoSelectedInitialSop.current = true;
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
    return (homepage?.most_viewed ?? []).map(toSearchResult);
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

  function navigateWorkspace(nextWorkspace: Workspace) {
    void navigate({ to: pathForWorkspace(nextWorkspace) });
  }

  function commandSearch(nextQuery: string) {
    const trimmedQuery = nextQuery.trim();
    if (!trimmedQuery) {
      return;
    }
    setQuery(trimmedQuery);
    runSearch(trimmedQuery);
    runRetrieval(trimmedQuery);
    navigateWorkspace("lookup");
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
        navigateWorkspace("lookup");
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

  function previewFileMetadata(file: File | null) {
    metadataPreviewMutation.reset();
    setUpload((current) => ({
      ...current,
      file,
      status: "draft",
      title: "",
      externalId: "",
      vertical: "",
      category: "",
      audience: "",
      tags: "",
      caseReasons: "",
      ownerTeam: current.ownerTeam || "CS Ops",
    }));
    if (!file) {
      return;
    }

    const form = new FormData();
    form.append("file", file);
    metadataPreviewMutation.mutate(form, {
      onSuccess: (preview) => {
        const metadata = preview.suggested_metadata;
        setUpload((current) => {
          if (current.file !== file) {
            return current;
          }
          return {
            ...current,
            title: preview.title || current.title || file.name,
            externalId: current.externalId || fileExternalId(file.name),
            vertical: metadata.vertical || current.vertical,
            category: metadata.category || current.category,
            audience: metadata.audience?.join(", ") || current.audience,
            tags: metadata.tags?.join(", ") || current.tags,
            caseReasons: metadata.case_reasons?.join(", ") || current.caseReasons,
            ownerTeam: metadata.owner_team || current.ownerTeam || "CS Ops",
            status: "draft",
          };
        });
        reportNotice(
          `Auto-filled metadata from ${preview.document_type}: ${preview.chunk_count} chunks, ${Math.round(preview.extraction_confidence * 100)}% confidence.`,
        );
      },
      onError: () => reportError("Could not auto-fill metadata. You can still enter the fields manually."),
    });
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
        audience: splitList(upload.audience),
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
        navigateWorkspace("documents");
      },
      onError: () => reportError("Upload failed. Confirm file type, size, and AI service health."),
    });
  }

  function publishVersion(versionId: string) {
    publishMutation.mutate(
      { versionId, actor: "cs-lead-ui" },
      {
        onSuccess: () => {
          setSelectedChunkVersionId(versionId);
          reportNotice("Version published. Previous published version was archived and Meilisearch was updated.");
        },
        onError: () =>
          reportError(
            "Publish blocked. Finish readiness checks first: full SOP, reviewed units, source refs, workflow graph, owner, effective date, and high-risk warnings.",
          ),
      },
    );
  }

  function bulkReviewVersion(versionId: string, scope: "all" | "atomic" = "all") {
    bulkReviewMutation.mutate(
      { versionId, actor: "cs-ops-ui", reviewStatus: "reviewed", scope },
      {
        onSuccess: () => {
          setSelectedChunkVersionId(versionId);
          reportNotice(
            scope === "atomic"
              ? "Atomic retrieval units marked reviewed. Review the full SOP page separately before publishing."
              : "Extraction units marked reviewed. Lead can publish after the remaining readiness checks pass.",
          );
        },
        onError: () => reportError("Bulk review failed. Only editable draft versions can be reviewed."),
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
    metadataPreviewMutation.isPending ? "metadata-preview" :
    uploadMutation.isPending ? "upload" :
    archiveDocumentMutation.isPending ? "archive-document" :
    createSynonymMutation.isPending ? "create-synonym" :
    syncSynonymsMutation.isPending ? "sync-synonyms" :
    generateSuggestionsMutation.isPending ? "generate-suggestions" :
    "";

  const appContext = {
    dashboardProps: {
      documents,
      homepage,
      onRunSearch: () => runSearch(),
      onWorkspaceChange: navigateWorkspace,
      query,
      setQuery,
      synonyms,
    },
    lookupProps: {
      aiSuggestion,
      booting: homepageQuery.isLoading,
      copied,
      copyError,
      feedbackRate: helpfulRate,
      filters,
      listSource,
      loading: searchMutation.isPending,
      onAskAI: askAI,
      onCopyMacro: copyMacro,
      onSelectDocumentMatch: (match: RetrievalResult) => {
        setSelectedDocumentMatch(match);
        setSelected(null);
      },
      onOpenSOP: openSOP,
      onRunSearch: () => runSearch(),
      onUpdateFilter: updateFilter,
      query,
      selected,
      selectedDocumentMatch,
      selectedVersion: selected?.current_version,
      semanticResults,
      setQuery,
    },
    retrievalProps: {
      busy: retrievalMutation.isPending,
      filters,
      mode: retrievalMode,
      onModeChange: setRetrievalMode,
      onRetrieve: () => runRetrieval(),
      onUpdateFilter: updateFilter,
      query,
      retrieval,
      setQuery,
    },
    documentsProps: {
      busyKey: busyKey || (publishMutation.isPending ? "publishing" : bulkReviewMutation.isPending ? "bulk-review" : ""),
      chunks,
      chunksLoading: chunksQuery.isFetching,
      documents,
      extractionUnits,
      extractionUnitsLoading: extractionUnitsQuery.isFetching,
      onArchiveDocument: archiveDocument,
      onInspectVersion: setSelectedChunkVersionId,
      onBulkReviewVersion: bulkReviewVersion,
      onPublishVersion: publishVersion,
      onRefreshDocuments: () => documentsQuery.refetch(),
      onSelectDocument: (documentId: string) => {
        const document = documents.find((item) => item.document_id === documentId);
        if (document) {
          setSelectedDocument(document);
          setSelectedChunkVersionId(document.latest_version_id ?? "");
        }
      },
      onUpdateExtractionUnit: updateExtractionUnit,
      onFileSelected: previewFileMetadata,
      onUpload: handleUpload,
      metadataPreview: metadataPreviewMutation.data ?? null,
      savingUnitId: updateExtractionUnitMutation.variables?.unitId ?? "",
      selectedDocument,
      selectedChunkVersionId,
      setSelectedDocument,
      setUpload,
      upload,
      versionRaw: versionRawQuery.data ?? null,
      versionRawLoading: versionRawQuery.isFetching,
      versions,
    },
    synonymsProps: {
      busyKey,
      draft: synonymDraft,
      onAcceptSuggestion: acceptSuggestion,
      onCreate: createSynonymGroup,
      onGenerateSuggestions: generateSuggestions,
      onRefreshSuggestions: () => suggestionsQuery.refetch(),
      onRefreshSynonyms: () => synonymsQuery.refetch(),
      onSetStatus: (status: string) => setSynonymStatus(status === "all" ? "" : status),
      onSync: syncSynonyms,
      onTransition: transitionSynonym,
      setDraft: setSynonymDraft,
      status: synonymStatus,
      suggestions,
      synonyms,
    },
  };

  return (
    <AppShell
      documentCount={documents.length}
      error={error || (homepageQuery.error ? "Cannot reach the API. Check Docker Compose and port 8080." : "")}
      latency={retrieval ? `${retrieval.latency_ms}ms` : "n/a"}
      notice={notice}
      onCommandSearch={commandSearch}
      onDismissError={() => setError("")}
      onDismissNotice={() => setNotice("")}
      onWorkspaceChange={navigateWorkspace}
      query={query}
      setQuery={setQuery}
      synonymCount={synonyms.length}
      workspace={workspace}
    >
      <KbAppProvider value={appContext}>
        <Outlet />
      </KbAppProvider>
    </AppShell>
  );
}

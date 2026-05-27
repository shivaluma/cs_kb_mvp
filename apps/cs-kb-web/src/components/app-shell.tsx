import { Link } from "@tanstack/react-router";
import {
	IconCommand as Command,
	IconMoon as Moon,
	IconSearch as Search,
	IconShieldCheck as ShieldCheck,
	IconSun as Sun,
	IconX as X
} from "@tabler/icons-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { StatusMessage } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDocuments } from "@/hooks/api/documents";
import { useOpsAnalytics } from "@/hooks/api/kb-index";
import {
	Sidebar,
	SidebarContent,
	SidebarGroup,
	SidebarGroupContent,
	SidebarGroupLabel,
	SidebarHeader,
	SidebarInset,
	SidebarMenu,
	SidebarMenuBadge,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarProvider,
	SidebarRail,
	SidebarTrigger,
	useSidebar,
} from "@/components/ui/sidebar";
import { commandNavGroups, navItems, sidebarNavGroups, type Workspace } from "@/constants";
import { cn } from "@/lib/utils";

const themeStorageKey = "cs-kb-theme";
const commandPaletteShortcut = "⌘K";
const commandPaletteAriaShortcut = "Meta+K Control+K";
const sidebarShortcut = "⌘B";
const sidebarAriaShortcut = "Meta+B Control+B";

function ShortcutKey({ children, className, title }: { children: ReactNode; className?: string; title?: string }) {
	return (
		<kbd
			className={cn(
				"inline-flex h-5 min-w-5 items-center justify-center rounded-md border bg-muted px-1.5 text-[10px] font-medium leading-none text-muted-foreground",
				className,
			)}
			title={title}
		>
			{children}
		</kbd>
	);
}

function getInitialDarkMode() {
	if (typeof window === "undefined") {
		return false;
	}

	try {
		const storedTheme = window.localStorage.getItem(themeStorageKey);
		if (storedTheme === "dark") {
			return true;
		}
		if (storedTheme === "light") {
			return false;
		}
	} catch {
		return false;
	}

	return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function MainSidebar({ workspace, reviewCount }: { workspace: Workspace; reviewCount: number }) {
	const { setOpenMobile } = useSidebar();
	const closeMobile = () => setOpenMobile(false);

	return (
		<Sidebar collapsible="icon" className="border-sidebar-border">
			<SidebarHeader className="px-3 py-3">
				<div className="flex min-h-10 items-center gap-2.5 rounded-xl px-1">
					<div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
						<ShieldCheck className="size-5" />
					</div>
					<div className="min-w-0 group-data-[collapsible=icon]:hidden">
						<p className="truncate text-sm font-semibold leading-tight">CS SOP KB</p>
						<p className="truncate text-[11px] leading-tight text-sidebar-foreground/60">
							Policy operations
						</p>
					</div>
				</div>
			</SidebarHeader>

			<SidebarContent className="px-1">
				{sidebarNavGroups.map((group) => (
					<SidebarGroup key={group.label}>
						<SidebarGroupLabel>{group.label}</SidebarGroupLabel>
						<SidebarGroupContent>
							<SidebarMenu>
								{group.items.map((item) => {
									const showBadge = item.id === "documents" && reviewCount > 0;
									return (
										<SidebarMenuItem key={item.id}>
											<SidebarMenuButton
												asChild
												isActive={workspace === item.id}
												tooltip={item.label}
											>
												<Link onClick={closeMobile} to={item.path}>
													<item.icon className="size-4" />
													<span>{item.label}</span>
												</Link>
											</SidebarMenuButton>
											{showBadge ? (
												<SidebarMenuBadge>
													{reviewCount > 99 ? "99+" : reviewCount}
												</SidebarMenuBadge>
											) : null}
										</SidebarMenuItem>
									);
								})}
							</SidebarMenu>
						</SidebarGroupContent>
					</SidebarGroup>
				))}
			</SidebarContent>
			<SidebarRail />
		</Sidebar>
	);
}

export function AppShell({
	children,
	error,
	notice,
	onCommandSearch,
	onDismissError,
	onDismissNotice,
	onWorkspaceChange,
	query,
	setQuery,
	workspace,
}: {
	children: ReactNode;
	error: string;
	notice: string;
	onCommandSearch: (query: string) => void;
	onDismissError: () => void;
	onDismissNotice: () => void;
	onWorkspaceChange: (workspace: Workspace) => void;
	query: string;
	setQuery: (query: string) => void;
	workspace: Workspace;
}) {
	const current = navItems.find((item) => item.id === workspace) ?? navItems[0];
	const [commandOpen, setCommandOpen] = useState(false);
	const [darkMode, setDarkMode] = useState(getInitialDarkMode);
	const [headerQuery, setHeaderQuery] = useState("");
	const documentsQuery = useDocuments();
	const analyticsQuery = useOpsAnalytics(14);

	const reviewCount = useMemo(() => {
		const docs = documentsQuery.data ?? [];
		return docs.filter(
			(doc) =>
				doc.status === "active" &&
				(doc.latest_review_status !== "approved" || doc.latest_version_status !== "published"),
		).length;
	}, [documentsQuery.data]);

	const quickQueries = useMemo(() => {
		const recent = (analyticsQuery.data?.recent_queries ?? []).map((item) => ({
			label: item.query,
			meta: "recent",
		}));
		const popular = (analyticsQuery.data?.popular_queries ?? []).map((item) => ({
			label: item.query,
			meta: `${item.count}x`,
		}));
		const seen = new Set<string>();
		return [...recent, ...popular]
			.filter((item) => {
				const key = item.label.trim().toLowerCase();
				if (!key || seen.has(key)) {
					return false;
				}
				seen.add(key);
				return true;
			})
			.slice(0, 6);
	}, [analyticsQuery.data]);

	useEffect(() => {
		const root = document.documentElement;
		root.classList.toggle("dark", darkMode);
		root.style.colorScheme = darkMode ? "dark" : "light";
		try {
			window.localStorage.setItem(themeStorageKey, darkMode ? "dark" : "light");
		} catch {
			// Storage failures are non-fatal; the current session still reflects the toggle.
		}
	}, [darkMode]);

	useEffect(() => {
		function onKeyDown(event: KeyboardEvent) {
			if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
				event.preventDefault();
				setCommandOpen((currentOpen) => !currentOpen);
			}
			if (event.key === "Escape") {
				setCommandOpen(false);
			}
		}
		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, []);

	function submitHeaderSearch() {
		const trimmed = headerQuery.trim();
		if (!trimmed) {
			return;
		}
		setQuery(trimmed);
		onCommandSearch(trimmed);
	}

	const isChatRoute = workspace === "chat";

	return (
		<main className="h-svh overflow-hidden bg-background text-foreground">
			<a
				className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
				href="#main-content"
			>
				Skip to main content
			</a>

			<SidebarProvider className="h-full min-h-0 overflow-hidden">
				<MainSidebar reviewCount={reviewCount} workspace={workspace} />

				<SidebarInset
					className="min-h-0 w-0 min-w-0 overflow-hidden"
					id="main-content"
				>
					<header className="shrink-0 border-b bg-background">
						<div className="flex items-center gap-3 px-4 py-3 md:px-6">
							<SidebarTrigger
								aria-keyshortcuts={sidebarAriaShortcut}
								aria-label="Toggle sidebar"
								className="shrink-0"
								title={`Toggle sidebar (${sidebarShortcut})`}
							/>
							<div className="min-w-0 flex-1">
								<div className="flex items-baseline gap-3">
									<h1 className="truncate text-base font-semibold leading-tight tracking-tight">
										{current.label}
									</h1>
									<p className="hidden truncate text-xs leading-tight text-muted-foreground sm:block">
										{current.description}
									</p>
								</div>
							</div>

							<div className="flex shrink-0 items-center gap-2">
								<div className="hidden md:block">
									<label
										className="flex h-9 w-72 items-center gap-2 rounded-full border bg-background pl-3 pr-1 text-sm transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30"
										htmlFor="global-search"
									>
										<Search className="size-4 shrink-0 text-muted-foreground" />
										<input
											className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
											id="global-search"
											onChange={(event) => setHeaderQuery(event.target.value)}
											onKeyDown={(event) => {
												if (event.key === "Enter") {
													event.preventDefault();
													submitHeaderSearch();
												}
											}}
											placeholder="Search SOPs, rules, macros…"
											value={headerQuery}
										/>
										<ShortcutKey className="hidden lg:inline-flex">
											{commandPaletteShortcut}
										</ShortcutKey>
									</label>
								</div>

								<Button
									aria-label="Open command palette"
									aria-keyshortcuts={commandPaletteAriaShortcut}
									className="md:hidden"
									onClick={() => setCommandOpen(true)}
									size="icon-sm"
									title={`Open command palette (${commandPaletteShortcut})`}
									type="button"
									variant="outline"
								>
									<Search className="size-4" />
								</Button>

								<Button
									aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
									onClick={() => setDarkMode((current) => !current)}
									size="icon-sm"
									type="button"
									variant="ghost"
								>
									{darkMode ? <Sun className="size-4" /> : <Moon className="size-4" />}
								</Button>

								<Button
									aria-keyshortcuts={commandPaletteAriaShortcut}
									className="hidden md:inline-flex"
									onClick={() => setCommandOpen(true)}
									size="sm"
									title={`Open command palette (${commandPaletteShortcut})`}
									type="button"
									variant="outline"
								>
									<Command data-icon="inline-start" className="size-4" />
									Command
									<ShortcutKey className="ml-1">
										{commandPaletteShortcut}
									</ShortcutKey>
								</Button>
							</div>
						</div>
						{notice || error ? (
							<div className="grid gap-2 px-4 pb-3 md:px-6">
								{notice ? (
									<StatusMessage
										tone="success"
										message={notice}
										onDismiss={onDismissNotice}
									/>
								) : null}
								{error ? (
									<StatusMessage
										tone="error"
										message={error}
										onDismiss={onDismissError}
									/>
								) : null}
							</div>
						) : null}
					</header>

					<div
						className={cn(
							"min-h-0 flex-1 overflow-y-auto",
							isChatRoute ? "" : "p-4 md:p-6",
						)}
					>
						{children}
					</div>
				</SidebarInset>
			</SidebarProvider>
			{commandOpen ? (
				<div
					aria-label="Command palette"
					aria-modal="true"
					className="fixed inset-0 z-50 bg-background/70 p-4 backdrop-blur-sm"
					role="dialog"
				>
					<div className="mx-auto mt-16 max-w-2xl overflow-hidden rounded-2xl border bg-popover shadow-xl">
						<div className="flex items-center gap-2 border-b px-3 py-3">
							<Search className="size-4 text-muted-foreground" />
							<Input
								autoFocus
								className="border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
								onChange={(event) => setQuery(event.target.value)}
								onKeyDown={(event) => {
									if (event.key === "Enter" && query.trim()) {
										onCommandSearch(query);
										setCommandOpen(false);
									}
								}}
								placeholder="Search SOP, rule, macro, case reason…"
								value={query}
							/>
							<div className="hidden items-center gap-1 sm:flex">
								<ShortcutKey title="Run search">
									Enter
								</ShortcutKey>
								<ShortcutKey title="Close command palette">
									Esc
								</ShortcutKey>
							</div>
							<Button
								aria-label="Close command palette"
								onClick={() => setCommandOpen(false)}
								size="icon"
								title="Close command palette (Esc)"
								type="button"
								variant="ghost"
							>
								<X className="size-4" />
							</Button>
						</div>
						<div className="grid gap-4 p-4 md:grid-cols-[1fr_0.9fr]">
							<section>
								<div className="mb-2 text-xs font-medium text-muted-foreground">Recent and popular</div>
								<div className="space-y-1">
									{quickQueries.map((item) => (
										<button
											className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
											key={item.label}
											onClick={() => {
												setQuery(item.label);
												onCommandSearch(item.label);
												setCommandOpen(false);
											}}
											type="button"
										>
											<span>{item.label}</span>
											<Badge variant="outline">{item.meta}</Badge>
										</button>
									))}
									{quickQueries.length === 0 ? (
										<div className="rounded-lg border bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
											Search history appears after agents use Lookup.
										</div>
									) : null}
								</div>
							</section>
							<section>
								<div className="mb-2 text-xs font-medium text-muted-foreground">Go to</div>
								<div className="space-y-3">
									{commandNavGroups.map((group) => (
										<div key={group.label}>
											<div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
												{group.label}
											</div>
											<div className="space-y-1">
												{group.items.map((item) => (
													<button
														className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
														key={item.id}
														onClick={() => {
															onWorkspaceChange(item.id);
															setCommandOpen(false);
														}}
														type="button"
													>
														<item.icon className="size-4 text-muted-foreground" />
														<span>{item.label}</span>
													</button>
												))}
											</div>
										</div>
									))}
								</div>
							</section>
						</div>
					</div>
				</div>
			) : null}
		</main>
	);
}

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
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarProvider,
	SidebarRail,
	SidebarSeparator,
	SidebarTrigger,
	useSidebar,
} from "@/components/ui/sidebar";
import { Switch } from "@/components/ui/switch";
import { documentWorkflowItems, navGroups, navItems, type Workspace } from "@/constants";
import { cn } from "@/lib/utils";

const themeStorageKey = "cs-kb-theme";

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

function MainSidebar({ workspace }: { workspace: Workspace }) {
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
						<p className="truncate text-sm font-semibold">CS SOP KB</p>
						<p className="truncate text-xs text-sidebar-foreground/60">
							Policy operations
						</p>
					</div>
				</div>
			</SidebarHeader>

			<SidebarContent className="px-1">
				{navGroups.map((group) => (
					<SidebarGroup key={group.label}>
						<SidebarGroupLabel>{group.label}</SidebarGroupLabel>
						<SidebarGroupContent>
							<SidebarMenu>
								{group.label === "Operations" ? (
									<DocumentWorkflowNav
										onNavigate={closeMobile}
										workspace={workspace}
									/>
								) : null}
								{group.items.map((item) => (
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
									</SidebarMenuItem>
								))}
							</SidebarMenu>
						</SidebarGroupContent>
					</SidebarGroup>
				))}

				<SidebarSeparator />

				<SidebarGroup className="group-data-[collapsible=icon]:hidden">
					<div className="rounded-lg border border-sidebar-border bg-background/70 p-3 text-xs leading-5 text-sidebar-foreground/70">
						<div className="font-medium text-sidebar-foreground">
							Production rule
						</div>
						Only published, approved versions should enter lookup and AI answer
						flows.
					</div>
				</SidebarGroup>
			</SidebarContent>
			<SidebarRail />
		</Sidebar>
	);
}

function DocumentWorkflowNav({
	onNavigate,
	workspace,
}: {
	onNavigate: () => void;
	workspace: Workspace;
}) {
	const workflowActive = documentWorkflowItems.some((item) => item.id === workspace);
	const WorkflowIcon = documentWorkflowItems[0].icon;
	const compactTarget = documentWorkflowItems.find((item) => item.id === workspace)?.path ?? documentWorkflowItems[1].path;

	return (
		<SidebarMenuItem>
			<div
				aria-label="Document workflow"
				className={cn(
					"rounded-xl border border-sidebar-border bg-sidebar/70 p-1.5 group-data-[collapsible=icon]:hidden",
					workflowActive && "border-sidebar-primary/30 bg-sidebar-accent/60",
				)}
				role="group"
			>
				<div className="flex items-center justify-between gap-2 px-2 pb-1 pt-1">
					<span className="truncate text-[11px] font-medium text-sidebar-foreground/70">
						Document workflow
					</span>
					<span className="text-[10px] tabular-nums text-sidebar-foreground/50">
						1-3
					</span>
				</div>
				<ol className="space-y-0.5">
					{documentWorkflowItems.map((item, index) => {
						const active = workspace === item.id;
						const label = item.id === "documents" ? "Review & publish" : item.label;
						return (
							<li key={item.id}>
								<Link
									className={cn(
										"flex h-8 items-center gap-2 rounded-lg px-2 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
										active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
									)}
									onClick={onNavigate}
									to={item.path}
								>
									<span
										className={cn(
											"flex size-5 shrink-0 items-center justify-center rounded-full border border-sidebar-border text-[10px] tabular-nums text-sidebar-foreground/60",
											active && "border-sidebar-primary bg-sidebar-primary text-sidebar-primary-foreground",
										)}
									>
										{index + 1}
									</span>
									<span className="truncate">{label}</span>
								</Link>
							</li>
						);
					})}
				</ol>
			</div>
			<SidebarMenuButton
				asChild
				className="hidden group-data-[collapsible=icon]:flex"
				isActive={workflowActive}
				tooltip="Document workflow"
			>
				<Link onClick={onNavigate} to={compactTarget}>
					<WorkflowIcon className="size-4" />
					<span>Document workflow</span>
				</Link>
			</SidebarMenuButton>
		</SidebarMenuItem>
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
	const analyticsQuery = useOpsAnalytics(14);
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
		return [...recent, ...popular].filter((item) => {
			const key = item.label.trim().toLowerCase();
			if (!key || seen.has(key)) {
				return false;
			}
			seen.add(key);
			return true;
		}).slice(0, 6);
	}, [analyticsQuery.data]);

	useEffect(() => {
		const root = document.documentElement;
		root.classList.toggle("dark", darkMode);
		root.style.colorScheme = darkMode ? "dark" : "light";

		try {
			window.localStorage.setItem(themeStorageKey, darkMode ? "dark" : "light");
		} catch {
			// Ignore storage failures so the switch still updates the current session.
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

	return (
		<main className="h-svh overflow-hidden bg-background text-foreground">
			<a
				className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
				href="#main-content"
			>
				Skip to main content
			</a>

			<SidebarProvider className="h-full min-h-0 overflow-hidden">
				<MainSidebar workspace={workspace} />

				<SidebarInset
					className="min-h-0 w-0 min-w-0 overflow-hidden"
					id="main-content"
				>
					<header className="shrink-0 border-b bg-background px-4 py-3 md:px-6">
						<div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
							<div className="flex min-w-0 gap-3">
								<SidebarTrigger className="mt-1 shrink-0" />
								<div className="min-w-0">
									<h1 className="text-xl font-semibold tracking-tight">
										{current.label}
									</h1>
									<p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">
										{current.description}
									</p>
								</div>
							</div>

							<div className="flex flex-wrap items-center gap-2">
								<div className="flex h-9 items-center gap-2 rounded-full border bg-background px-2.5">
									<Sun
										aria-hidden="true"
										className={
											darkMode
												? "size-3.5 text-muted-foreground"
												: "size-3.5 text-foreground"
										}
									/>
									<Switch
										aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
										checked={darkMode}
										onCheckedChange={setDarkMode}
										size="sm"
									/>
									<Moon
										aria-hidden="true"
										className={
											darkMode
												? "size-3.5 text-foreground"
												: "size-3.5 text-muted-foreground"
										}
									/>
								</div>
								<Button
									onClick={() => setCommandOpen(true)}
									type="button"
									variant="outline"
								>
									<Command data-icon="inline-start" className="size-4" />
									Command
									<span className="ml-1 rounded border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">⌘K</span>
								</Button>
							</div>
						</div>
						{notice || error ? (
							<div className="mt-3 grid gap-2">
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

					<div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-5">
						{children}
					</div>
				</SidebarInset>
			</SidebarProvider>
			{commandOpen ? (
				<div
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
								placeholder="Search SOP, rule, macro, case reason..."
								value={query}
							/>
							<Button
								aria-label="Close command palette"
								onClick={() => setCommandOpen(false)}
								size="icon"
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
									{navGroups.map((group) => (
										<div key={group.label}>
											<div className="px-2 pb-1 text-[11px] font-medium text-muted-foreground">{group.label}</div>
											<div className="space-y-1">
												{group.label === "Operations" ? (
													<div className="mb-1 rounded-lg border bg-muted/15 p-1.5">
														<div className="flex items-center justify-between gap-2 px-2 pb-1 text-[11px] font-medium text-muted-foreground">
															<span>Document workflow</span>
															<span className="tabular-nums">1-3</span>
														</div>
														<div className="space-y-0.5">
															{documentWorkflowItems.map((item, index) => (
																<button
																	className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
																	key={item.id}
																	onClick={() => {
																		onWorkspaceChange(item.id);
																		setCommandOpen(false);
																	}}
																	type="button"
																>
																	<span className="flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px] tabular-nums text-muted-foreground">
																		{index + 1}
																	</span>
																	<span>{item.id === "documents" ? "Review & publish" : item.label}</span>
																</button>
															))}
														</div>
													</div>
												) : null}
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

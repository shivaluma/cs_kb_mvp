import { Link } from "@tanstack/react-router";
import { Bell, CircleHelp, Command, Moon, Search, ShieldCheck, Sun, X } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { StatusMessage } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { navItems, type Workspace } from "@/constants";

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
				<SidebarGroup>
					<SidebarGroupLabel>Main</SidebarGroupLabel>
					<SidebarGroupContent>
						<SidebarMenu>
							{navItems.map((item) => (
								<SidebarMenuItem key={item.id}>
									<SidebarMenuButton
										asChild
										isActive={workspace === item.id}
										tooltip={item.label}
									>
										<Link onClick={() => setOpenMobile(false)} to={item.path}>
											<item.icon className="size-4" />
											<span>{item.label}</span>
										</Link>
									</SidebarMenuButton>
								</SidebarMenuItem>
							))}
						</SidebarMenu>
					</SidebarGroupContent>
				</SidebarGroup>

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

export function AppShell({
	children,
	documentCount,
	error,
	latency,
	notice,
	onCommandSearch,
	onDismissError,
	onDismissNotice,
	onWorkspaceChange,
	query,
	setQuery,
	synonymCount,
	workspace,
}: {
	children: ReactNode;
	documentCount: number;
	error: string;
	latency: string;
	notice: string;
	onCommandSearch: (query: string) => void;
	onDismissError: () => void;
	onDismissNotice: () => void;
	onWorkspaceChange: (workspace: Workspace) => void;
	query: string;
	setQuery: (query: string) => void;
	synonymCount: number;
	workspace: Workspace;
}) {
	const current = navItems.find((item) => item.id === workspace) ?? navItems[0];
	const [commandOpen, setCommandOpen] = useState(false);
	const [darkMode, setDarkMode] = useState(getInitialDarkMode);
	const quickQueries = useMemo(
		() => ["gmai.com thì làm gì", "lỗi ZT email", "KH không nhận được email", "email sai định dạng khác"],
		[],
	);

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
									<div className="text-xs text-muted-foreground">
										CS Knowledge Base
									</div>
									<h1 className="mt-0.5 text-xl font-semibold tracking-tight">
										{current.label}
									</h1>
									<p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">
										{current.description}
									</p>
								</div>
							</div>

							<div className="flex flex-wrap items-center gap-2">
								<Badge variant="outline">{documentCount} docs</Badge>
								<Badge variant="outline">{synonymCount} synonym groups</Badge>
								<Badge variant="outline">retrieval {latency}</Badge>
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
								<Button
									aria-label="Help"
									size="icon"
									type="button"
									variant="ghost"
								>
									<CircleHelp className="size-4" />
								</Button>
								<Button
									aria-label="Notifications"
									size="icon"
									type="button"
									variant="ghost"
								>
									<Bell className="size-4" />
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
								<div className="mb-2 text-xs font-medium text-muted-foreground">Quick searches</div>
								<div className="space-y-1">
									{quickQueries.map((item) => (
										<button
											className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
											key={item}
											onClick={() => {
												setQuery(item);
												onCommandSearch(item);
												setCommandOpen(false);
											}}
											type="button"
										>
											<span>{item}</span>
											<Badge variant="outline">search</Badge>
										</button>
									))}
								</div>
							</section>
							<section>
								<div className="mb-2 text-xs font-medium text-muted-foreground">Go to</div>
								<div className="space-y-1">
									{navItems.map((item) => (
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
							</section>
						</div>
					</div>
				</div>
			) : null}
		</main>
	);
}

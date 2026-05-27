import assert from "node:assert/strict";
import test from "node:test";

import { buildNavGroups, commandGroupSpecs, sidebarGroupSpecs } from "./navigation-model.ts";

const items = [
  "dashboard",
  "lookup",
  "chat",
  "caseAssist",
  "collections",
  "tools",
  "operations",
  "documents",
  "documentUpload",
  "documentQueue",
  "feedback",
  "relations",
  "synonyms",
  "retrieval",
].map((id) => ({ id, label: id }));

test("sidebar navigation keeps daily knowledge work visible and hides setup/debug routes", () => {
  const groups = buildNavGroups(items, sidebarGroupSpecs);
  const ids = groups.flatMap((group) => group.items.map((item) => item.id));

  assert.deepEqual(groups.map((group) => group.label), ["Daily workspace", "Knowledge", "Review"]);
  assert.ok(ids.includes("lookup"));
  assert.ok(ids.includes("documents"));
  assert.ok(ids.includes("documentUpload"));
  assert.ok(ids.includes("documentQueue"));
  assert.ok(!ids.includes("operations"));
  assert.ok(!ids.includes("synonyms"));
  assert.ok(!ids.includes("retrieval"));
});

test("command navigation keeps every real destination reachable", () => {
  const groups = buildNavGroups(items, commandGroupSpecs);
  const ids = new Set(groups.flatMap((group) => group.items.map((item) => item.id)));

  assert.equal(ids.size, items.length);
  for (const item of items) {
    assert.ok(ids.has(item.id), `${item.id} should be present in command navigation`);
  }
});

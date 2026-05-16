export type ReviewFrequency = "annual" | "quarterly" | "semiannual" | string;

export function formatIsoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseIsoDate(value: string) {
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return undefined;
  }
  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  const date = new Date(year, month, day);
  if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) {
    return undefined;
  }
  return date;
}

export function todayIsoDate(now = new Date()) {
  return formatIsoDate(new Date(now.getFullYear(), now.getMonth(), now.getDate()));
}

export function nextReviewDueIso(lastReviewedAt: string, reviewFrequency: ReviewFrequency, now = new Date()) {
  const baseDate = parseIsoDate(lastReviewedAt) ?? parseIsoDate(todayIsoDate(now));
  if (!baseDate) {
    return "";
  }
  const months = reviewFrequencyMonths(reviewFrequency);
  if (!months) {
    return "";
  }
  return formatIsoDate(addMonthsClamped(baseDate, months));
}

export function withReviewFrequencyDates<T extends { lastReviewedAt: string; nextReviewDue: string; reviewFrequency: string }>(
  current: T,
  reviewFrequency: string,
  now = new Date(),
): T {
  if (!reviewFrequency) {
    return { ...current, reviewFrequency };
  }
  const lastReviewedAt = parseIsoDate(current.lastReviewedAt) ? current.lastReviewedAt : todayIsoDate(now);
  return {
    ...current,
    lastReviewedAt,
    nextReviewDue: nextReviewDueIso(lastReviewedAt, reviewFrequency, now),
    reviewFrequency,
  };
}

function reviewFrequencyMonths(reviewFrequency: ReviewFrequency) {
  const map: Record<string, number> = {
    annual: 12,
    quarterly: 3,
    semiannual: 6,
  };
  return map[String(reviewFrequency).trim().toLowerCase()] ?? 0;
}

function addMonthsClamped(date: Date, months: number) {
  const target = new Date(date.getFullYear(), date.getMonth() + months, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(date.getDate(), lastDay));
  return target;
}

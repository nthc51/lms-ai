import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type Question = S["QuestionOut"];
export type ReviewStatus = S["ReviewStatus"];
export type Difficulty = S["Difficulty"];
export type Quiz = S["QuizOut"];
export type Attempt = S["AttemptOut"];
export type AttemptResult = S["AttemptResult"];
export type CourseAnalytics = S["CourseAnalytics"];

export const DIFFICULTY_LABEL: Record<Difficulty, string> = { easy: "Dễ", medium: "Vừa", hard: "Khó" };

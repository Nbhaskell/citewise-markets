// Named aliases for the types generated from the API (src/api/schema.d.ts, made by `npm run gen:api`).
import type { components } from "./schema";

type S = components["schemas"];

export type StockSummary = S["StockSummary"];
export type StockDetail = S["StockDetail"];
export type FilingOut = S["FilingOut"];
export type PricePoint = S["PricePoint"];
export type SentimentSummary = S["SentimentSummary"];
export type PriceSeries = S["PriceSeries"];
export type NewsFeedItem = S["NewsFeedItem"];
export type CopilotRequest = S["CopilotRequest"];
export type HistoryTurn = S["HistoryTurn"];
export type CopilotResponse = S["CopilotResponse"];
export type CopilotSource = S["Source"];
export type StatusOut = S["StatusOut"];
export type Fundamentals = S["FundamentalsOut"];
export type FundamentalFigure = S["FundamentalFigure"];
export type Health = S["Health"];
export type AddLookupOut = S["AddLookupOut"];
export type AddJobOut = S["AddJobOut"];
export type ReportCompany = S["ReportCompany"];
export type ChangesOut = S["ChangesOut"];
export type ChangeMove = S["ChangeMove"];
export type ChangeFiling = S["ChangeFiling"];
export type ChangeCompanyNews = S["ChangeCompanyNews"];

export type PriceRange = "1M" | "3M" | "6M" | "1Y" | "5Y" | "MAX";
export type NewsLabel = "positive" | "negative" | "neutral";

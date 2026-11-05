export type PromptActivity = {
  org_prompt_id: number;
  optimized_prompt_id?: number | null;
  org_prompt_txt: string;
  org_prompt_input_time: string;
  org_prompt_tokens: number | null;
  optimized_prompt_tokens: number | null;
  optimized_prompt_txt: string | null;
  optimized_prompt_creation_time: string | null;
  tokens_saved: number | null;
  percent_saved: number | null;
  severity?: string | null;
  target: string;
};

export interface DramaImportRow {
  source_row: number
  drama_name: string
  platform: string
  available_time: string
  has_validated_links: boolean
}

export interface DramaImportError {
  source_row: number
  message: string
}

export interface DramaImportOperator {
  name: string
  group_prefix: string
}

export interface DramaImportPreview {
  preview_id: string
  business_date: string
  source_count: number
  new_count: number
  duplicate_count: number
  invalid_count: number
  rows: DramaImportRow[]
  errors: DramaImportError[]
}

export interface DramaImportRun {
  run_id: string
  status: "PREVIEWED" | "RUNNING" | "COMPLETED" | "FAILED"
  business_date: string
  source_count: number
  new_count: number
  duplicate_count: number
  invalid_count: number
  inserted_count: number
  inserted_rows: number[]
  verified: boolean
  error_message: string | null
}

export interface ImportedDramaRecord {
  source_key: string
  drama_name: string
  platform: string
  available_time: string
  operator_name: string
  task_id: string | null
  task_status: string | null
}

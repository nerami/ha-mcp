export interface Interrupt {
  id: string;
  toolCallId?: string;
  reason?: string;
  message?: string;
}

export interface RunFinishedOutcome {
  type: string;
  interrupts?: Interrupt[];
}

export type AgUiEvent =
  | { type: "RUN_STARTED" }
  | { type: "TEXT_MESSAGE_START"; messageId: string; role?: string }
  | { type: "TEXT_MESSAGE_CONTENT"; messageId: string; delta: string }
  | { type: "TEXT_MESSAGE_END"; messageId: string }
  | {
      type: "TOOL_CALL_START";
      toolCallId: string;
      toolCallName: string;
      parentMessageId?: string;
    }
  | { type: "TOOL_CALL_ARGS"; toolCallId: string; delta: string }
  | { type: "TOOL_CALL_END"; toolCallId: string }
  | {
      type: "TOOL_CALL_RESULT";
      messageId: string;
      toolCallId: string;
      content: string;
    }
  | { type: "RUN_FINISHED"; outcome?: RunFinishedOutcome }
  | { type: "RUN_ERROR"; message: string }
  | { type: string };

import { useContext } from "react";
import { ChatContext } from "./ChatContextBase";

export function useChatContext() {
  const context = useContext(ChatContext);
  if (!context) throw new Error("useChatContext must be used inside ChatProvider.");
  return context;
}

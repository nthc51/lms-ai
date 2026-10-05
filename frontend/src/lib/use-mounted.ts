import * as React from "react";

const noop = () => () => {};

/** true sau khi hydrate xong trên trình duyệt; false khi render phía server. */
export function useMounted() {
  return React.useSyncExternalStore(noop, () => true, () => false);
}

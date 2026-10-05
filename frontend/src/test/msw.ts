import { setupServer } from "msw/node";

// Mỗi test tự thêm handler bằng server.use(...). Base URL của jsdom là http://localhost:3000.
export const server = setupServer();
export const api = (path: string) => `http://localhost:3000/api/v1${path}`;

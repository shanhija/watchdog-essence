// Run the ingest job once. It processes the record batch and writes its logs
// (including the errors caused by the bug) to app.log.
import { main } from "./app/ingest.ts";

main();

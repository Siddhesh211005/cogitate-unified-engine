import Link from "next/link";
import { ArrowRight, Database, PlayCircle } from "lucide-react";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4 sm:p-8 bg-slate-50 dark:bg-slate-900">
      <div className="absolute top-0 left-0 w-full h-1.5 bg-orange-600"></div>
      
      <div className="w-full max-w-4xl space-y-12 text-center animate-in fade-in slide-in-from-bottom-8 duration-700 mt-10">
        
        <header className="space-y-4">
          <div className="inline-flex items-center justify-center px-4 py-1 mb-6 text-xs font-bold tracking-widest uppercase rounded-full bg-orange-100 text-orange-600 border border-orange-200">
            COM Engine Powered
          </div>
          <h1 className="text-5xl sm:text-7xl font-extrabold tracking-tight text-slate-800 dark:text-white">
            Cogitate <span className="text-orange-600">Excel Rater</span>
          </h1>
          <p className="max-w-2xl mx-auto text-lg sm:text-xl text-slate-500 mt-6 font-medium">
            Upload actuarial Microsoft Excel models, automatically parse schemas, and instantly generate live web interfaces.
          </p>
        </header>

        <section className="grid gap-6 md:grid-cols-2 text-left pt-8 max-w-3xl mx-auto">
          
          <Link
            href="/admin"
            className="group relative flex flex-col justify-between overflow-hidden rounded-2xl border border-slate-200 bg-white p-8 shadow-sm transition hover:shadow-md hover:border-orange-600"
          >
            <div className="mb-4 text-orange-600 bg-orange-50 w-12 h-12 rounded-xl flex items-center justify-center border border-orange-100">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-800">Admin Portal</h2>
              <p className="mt-3 text-slate-500 font-medium leading-relaxed">
                Transform new workbooks into live APIs. Upload Excel files, verify extracted _Schema mappings, and establish new system records.
              </p>
            </div>
            <div className="mt-8 flex items-center text-sm font-bold tracking-wide text-orange-600">
              ACCESS ADMIN <ArrowRight className="ml-2 w-4 h-4 transition-transform group-hover:translate-x-1" />
            </div>
          </Link>

          <Link
            href="/client"
            className="group relative flex flex-col justify-between overflow-hidden rounded-2xl border border-slate-200 bg-white p-8 shadow-sm transition hover:shadow-md hover:border-orange-600"
          >
            <div className="mb-4 text-orange-600 bg-orange-50 w-12 h-12 rounded-xl flex items-center justify-center border border-orange-100">
              <PlayCircle className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-800">Client Panel</h2>
              <p className="mt-3 text-slate-500 font-medium leading-relaxed">
                Select a recorded Microsoft Excel matrix, input parameters dynamically, and compute lightning-fast premiums. 
              </p>
            </div>
            <div className="mt-8 flex items-center text-sm font-bold tracking-wide text-orange-600">
              LAUNCH CLIENT <ArrowRight className="ml-2 w-4 h-4 transition-transform group-hover:translate-x-1" />
            </div>
          </Link>

        </section>
      </div>
    </main>
  );
}

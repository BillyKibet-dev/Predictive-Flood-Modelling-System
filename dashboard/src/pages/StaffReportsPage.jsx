import TopNav from '../components/TopNav'
import ReportReviewQueue from '../components/ReportReviewQueue'
export default function StaffReportsPage() {
  return (
    <div className="min-h-screen bg-bg">
      <TopNav variant="app" active="Reports" />
      <main className="max-w-5xl mx-auto p-6">
        <ReportReviewQueue />
      </main>
    </div>
  )
}

'use client';

import CustomLogo from '@/components/custom-logo';
import UploadStep from '@/components/upload-step';
import { useRouter } from 'next/navigation';

export default function StartPage() {
  const router = useRouter();

  const handleBackToHome = () => {
    router.push('/');
  };

  return (
    <div className="h-screen w-full bg-black flex flex-col overflow-hidden">
      <div className="flex-1 overflow-auto flex flex-col">
        <div className="flex justify-center pt-10">
          <CustomLogo size="lg" text="AI Slides" />
        </div>

        <div className="flex-1">
          <UploadStep onBack={handleBackToHome} />
        </div>
      </div>
    </div>
  );
}

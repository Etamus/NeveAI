<script>
    import { onMount } from 'svelte';
    import PDFViewer from '../../src/lib/components/common/PDFViewer.svelte';
    let data = null;
    onMount(async () => {
        const { jsPDF } = await import('jspdf');
        const pdf = new jsPDF();
        pdf.text('PDF zoom and scroll regression', 20, 20);
        data = new Uint8Array(pdf.output('arraybuffer'));
    });
</script>
<div style="padding:24px;background:#171717;min-height:100vh">
    <div id="pdf-frame" style="width:min(100%,500px);height:350px;background:#171717">
        {#if data}<PDFViewer {data} className="w-full h-full" />{/if}
    </div>
    <div id="document-scroll" style="width:300px;height:160px;overflow:auto;background:#171717;margin-top:20px">
        <div style="width:600px;height:400px">Document preview</div>
    </div>
</div>

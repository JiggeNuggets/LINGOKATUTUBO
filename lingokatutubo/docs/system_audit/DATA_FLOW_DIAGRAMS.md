# LingoKatutubo System Data Flow Diagrams

This document contains Data Flow Diagrams (DFDs) modeling the data pathways, processes, external entities, and data stores within the LingoKatutubo system.

## DFD Level 0: Context Diagram

This level shows the system as a single process interacting with its external environment.

```mermaid
flowchart TD
    %% External Entities
    Guest[Guest User]
    AuthUser[Authenticated User]
    Validator[Validator]
    Admin[Administrator]
    Tesseract[Tesseract OCR Binary]

    %% System
    System((LingoKatutubo\nSystem))

    %% Flows
    Guest -->|Quick translate text,\nRegistration data| System
    System -->|Quick translation result,\nRegistration status| Guest
    
    AuthUser -->|Login credentials,\nDocument uploads,\nCorrection suggestions| System
    System -->|Translated PDFs,\nBilingual PDFs,\nPreview images,\nTranslation status,\nJob history| AuthUser
    
    Validator -->|Validation decisions| System
    System -->|Validation queue data| Validator
    
    Admin -->|Configurations| System
    System -->|System health data| Admin
    
    System <-->|Image data for OCR /\nExtracted text & confidence scores| Tesseract
```

## DFD Level 1: Major Processes

This diagram expands the system into its primary functional processes.

```mermaid
flowchart TD
    %% External Entities
    User[User]
    Validator[Validator]
    Admin[Administrator]
    Tesseract[Tesseract OCR Binary]

    %% Data Stores
    DS1[(Django User Table)]
    DS2[(TranslationJob / UploadedDocument)]
    DS3[(DocumentPage / OCRResult)]
    DS4[(PhrasebookEntry / TranslationSegment)]
    DS5[(UnknownTranslationRecord)]
    DS6[(GeneratedOutput)]
    DS7[(LanguageEntryReview / PhrasebookEntryRevision)]
    DS8[(SystemEventLog / UserActivityLog)]

    %% Processes
    P1((P1: User Authentication))
    P2((P2: Document Upload Mgmt))
    P3((P3: Text Extraction & OCR))
    P4((P4: Translation & Phrase Matching))
    P5((P5: Unknown Word Processing))
    P6((P6: Document Reconstruction))
    P7((P7: Validation & Review))
    P8((P8: History & Output Mgmt))
    P9((P9: Administration))
    P10((P10: Audit Logging))

    %% Flows
    User -->|Credentials| P1
    P1 <-->|Auth checks| DS1
    P1 -.->|Events| P10

    User -->|Uploads| P2
    P2 -->|Job metadata| DS2
    P2 -.->|Events| P10

    P2 -->|Dispatch Job| P3
    P3 <-->|Process Image| Tesseract
    P3 -->|Extracted Text| DS3
    
    P3 -->|Text Data| P4
    P4 <-->|Lookups| DS4
    
    P4 -->|Untranslated Segments| P5
    P5 -->|Unknown Records| DS5
    
    P4 -->|Translated Data| P6
    P6 -->|Output Files info| DS6
    
    User <-->|View/Download| P8
    P8 <-->|Read| DS2
    P8 <-->|Read| DS6
    
    Validator -->|Decisions| P7
    P7 <-->|Reviews| DS7
    P7 <-->|Update Status| DS4

    Admin <-->|Manage models| P9
    P10 -->|Logs| DS8
```

## DFD Level 2: Document Processing Pipeline

This diagram breaks down the core translation pipeline processes (`P2`, `P3`, `P4`, `P5`, `P6`).

```mermaid
flowchart TD
    %% External
    Tesseract[Tesseract OCR Binary]
    FileSystem[(MEDIA_ROOT /jobs/{id}/)]

    %% Data Stores
    DS_Job[(TranslationJob)]
    DS_UpDoc[(UploadedDocument)]
    DS_DocPage[(DocumentPage)]
    DS_OCR[(OCRResult)]
    DS_Phrase[(PhrasebookEntry / translation_data.json)]
    DS_Segment[(TranslationSegment)]
    DS_Unknown[(UnknownTranslationRecord)]
    DS_Output[(GeneratedOutput)]

    %% Processes
    subgraph P2 [P2: Document Upload Management]
        P2.1((P2.1: Receive Upload\nValidate form/file))
        P2.2((P2.2: Start Background Job))
    end

    subgraph P3 [P3: Text Extraction & OCR]
        P3.1((P3.1: Detect Document Type))
        P3.2((P3.2: Extract Digital Text))
        P3.3((P3.3: Extract OCR Text))
        P3.4((P3.4: Create Records))
    end

    subgraph P4 [P4: Translation & Phrase Matching]
        P4.1((P4.1: Rebuild Sentences))
        P4.2((P4.2: Phrasebook Cascade Lookup))
        P4.3((P4.3: Neural Fallback))
        P4.4((P4.4: Create TranslationSegment))
    end

    subgraph P5 [P5: Unknown Word Processing]
        P5.1((P5.1: Identify Unknown Segments))
    end

    subgraph P6 [P6: Document Reconstruction]
        P6.1((P6.1: Redact Original Text))
        P6.2((P6.2: Draw Translated Text))
        P6.3((P6.3: Generate Preview PNGs))
        P6.4((P6.4: Generate Bilingual PDF))
        P6.5((P6.5: Create GeneratedOutput))
    end

    %% Flows
    User_Input[/Document Upload/] --> P2.1
    P2.1 -->|Save to disk| FileSystem
    P2.1 -->|Write| DS_Job
    P2.1 -->|Write| DS_UpDoc
    P2.1 -->|Trigger| P2.2
    
    P2.2 -->|Dispatch| P3.1
    P3.1 --> P3.2
    P3.1 --> P3.3
    P3.3 <-->|Image / Confidence scores| Tesseract
    P3.2 --> P3.4
    P3.3 --> P3.4
    P3.4 -->|Write| DS_DocPage
    P3.4 -->|Write| DS_OCR
    
    P3.4 -->|Pass Extracted text| P4.1
    P4.1 --> P4.2
    P4.2 <-->|Read Exact/Normalized/Fuzzy| DS_Phrase
    P4.2 --> P4.3
    P4.3 --> P4.4
    P4.4 -->|Write| DS_Segment
    
    P4.4 --> P5.1
    P5.1 -->|Write untranslatable| DS_Unknown
    
    P4.4 --> P6.1
    P6.1 --> P6.2
    P6.2 --> P6.3
    P6.2 --> P6.4
    P6.3 -->|Render PNGs| FileSystem
    P6.4 -->|Alternating pages| FileSystem
    P6.4 --> P6.5
    P6.3 --> P6.5
    P6.5 -->|Write| DS_Output
```

## DFD Level 2: Validation & Review

This diagram details the `P7` process for handling terminology validation.

```mermaid
flowchart TD
    %% External
    Validator[Validator]

    %% Data Stores
    DS_Phrase[(PhrasebookEntry)]
    DS_Review[(LanguageEntryReview)]
    DS_Revision[(PhrasebookEntryRevision)]

    %% Processes
    subgraph P7 [P7: Validation & Review]
        P7.1((P7.1: Load Validator Queue))
        P7.2((P7.2: Display Entry Details))
        P7.3((P7.3: Record Decision))
        P7.4((P7.4: Check Eligibility))
    end

    %% Flows
    Validator -->|Requests pending entries| P7.1
    P7.1 <-->|Filter by status| DS_Phrase
    P7.1 --> P7.2
    P7.2 <-->|Fetch history| DS_Revision
    P7.2 <-->|Fetch past reviews| DS_Review
    P7.2 -->|Display| Validator
    
    Validator -->|Submit Approve/Reject| P7.3
    P7.3 -->|Create| DS_Review
    P7.3 --> P7.4
    P7.4 -->|Check runtime eligible| DS_Phrase
```

## Data Flow Dictionary

| Data Flow | Source | Destination | Contents | Validation | Storage | Evidence |
|---|---|---|---|---|---|---|
| **Document Upload** | External Entity (User) | P2.1 | File binaries, target language, user info | File extension, MIME type, size limit, authentication | Local FileSystem | `EV-001`, `EV-008` |
| **Dispatch Job** | P2.2 | P3.1 | TranslationJob ID | Ensure Job state is PENDING | Queue/DB (`TranslationJob`) | `EV-002` |
| **Extracted Text & BBoxes** | P3.4 | P4.1, `DS_DocPage`, `DS_OCR` | Geometric bboxes, text content, OCR confidence | Coordinate validation, string encoding | DB (`DocumentPage`, `OCRResult`) | `EV-003`, `EV-004` |
| **Match Candidates** | `DS_Phrase` | P4.2 | Phrasebook definitions, target terms | Dataset schema match | DB / JSON | `EV-006` |
| **Translation Output** | P4.4 | P6.1, `DS_Segment` | Original segment, translated segment, bounding box mapping | String mapping integrity | DB (`TranslationSegment`) | `EV-008` |
| **Unknown Segment** | P5.1 | `DS_Unknown` | Untranslatable word/phrase text, language pair | Context constraints | DB (`UnknownTranslationRecord`) | `EV-008` |
| **Rendered Files** | P6.3, P6.4 | `DS_Output`, FileSystem | Reconstructed PDF files, preview PNGs | Output success validation, path existence | FileSystem / DB (`GeneratedOutput`) | `EV-005` |
| **Review Decision** | External Entity (Validator) | P7.3 | Approve/Reject status, optional feedback | Role authorization, valid entry ID | DB (`LanguageEntryReview`) | `EV-007` |

## Evidence Reference

*   **`EV-001`**: `views.py` - Manages incoming requests, document uploads, and authentication.
*   **`EV-002`**: `pipeline_service.py` - Orchestrates the background dispatch and sequential execution of P3-P6.
*   **`EV-003`**: `extraction_service.py` - Handles digital document processing and routing.
*   **`EV-004`**: `ocr_service.py` - Manages interaction with Tesseract and structuring OCR results.
*   **`EV-005`**: `reconstruction_service.py` - Handles redacting, drawing text, and outputting new files.
*   **`EV-006`**: `translation_dataset.py` - Loads and filters phrasebook matching data.
*   **`EV-007`**: `governance.py` - Business logic for reviews, decisions, and runtime eligibility.
*   **`EV-008`**: `models.py` - Core schema definitions for all database tables used in the flows.

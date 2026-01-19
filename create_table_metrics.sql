USE wildfires;

CREATE TABLE metrics (
    id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
    
    acq_datetime TIMESTAMP NOT NULL,
    gcs_path VARCHAR(2048) NOT NULL,
    metric VARCHAR(50) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
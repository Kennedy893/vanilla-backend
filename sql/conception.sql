CREATE TABLE organizations(
   id SERIAL,
   name VARCHAR(50) ,
   organization_type VARCHAR(50)  NOT NULL
    CHECK (organization_type IN (
        'producer',
        'collector',
        'cooperative',
        'processor',
        'transporter',
        'exporter',
        'certification_body',
        'other'
    )),
   address VARCHAR(50) ,
   is_active BOOLEAN,
   created_at TIMESTAMP DEFAULT NOW(),
   phone VARCHAR(50) ,
   PRIMARY KEY(id)
);

CREATE TABLE users(
   id SERIAL,
   username VARCHAR(50)  NOT NULL,
   email VARCHAR(50) ,
   password VARCHAR(255)  NOT NULL,
   is_active BOOLEAN NOT NULL,
   created_at TIMESTAMP DEFAULT NOW(),
   UNIQUE(username, email),
   PRIMARY KEY(id)
);

CREATE TABLE organization_members(
   id SERIAL,
   role VARCHAR(50)  NOT NULL
    CHECK (role IN (
        'owner',
        'manager',
        'operator',
        'viewer'
    )),
   joined_at TIMESTAMP,
   user_id INTEGER NOT NULL,
   organization_id INTEGER NOT NULL,
   UNIQUE(user_id, organization_id),
   PRIMARY KEY(id),
   FOREIGN KEY(user_id) REFERENCES users(id),
   FOREIGN KEY(organization_id) REFERENCES organizations(id)
);

CREATE TABLE locations(
   id SERIAL,
   name VARCHAR(50)  NOT NULL,
   location_type VARCHAR(50) ,
   latitude NUMERIC(9,6)  ,
   longitude NUMERIC(9,6)  ,
   PRIMARY KEY(id)
);

CREATE TABLE farms(
   id SERIAL,
   farm_code VARCHAR(50) ,
   name VARCHAR(50) ,
   area_hectares NUMERIC(15,2) CHECK (area_hectares >= 0) ,
   created_at TIMESTAMP DEFAULT NOW(),
   producer_organization_id INTEGER NOT NULL,
   location_id INTEGER NOT NULL,
   PRIMARY KEY(id),
   UNIQUE(farm_code),
   FOREIGN KEY(producer_organization_id) REFERENCES organizations(id),
   FOREIGN KEY(location_id) REFERENCES locations(id)
);

CREATE TABLE lots(
   id SERIAL,
   lot_code VARCHAR(50) ,
   lot_type VARCHAR(50)  NOT NULL
    CHECK (lot_type IN (
        'harvest',
        'raw',
        'intermediate',
        'finished'
    )),
   product_state VARCHAR(50)
    CHECK (product_state IN (
        'fresh',
        'fermenting',
        'dried',
        'sorted',
        'graded',
        'packaged'
    )) ,
   quantity_kg NUMERIC(15,2) CHECK (quantity_kg >= 0) ,
   status VARCHAR(50) 
    CHECK (status IN (
        'created',
        'available',
        'in_transfer',
        'processing',
        'blocked',
        'exported',
        'archived'
    )),
   created_at TIMESTAMP DEFAULT NOW(),
   updated_at TIMESTAMP,
   farm_id INTEGER NOT NULL,
   holder_id INTEGER NOT NULL,
   PRIMARY KEY(id),
   UNIQUE(lot_code),
   FOREIGN KEY(farm_id) REFERENCES farms(id),
   FOREIGN KEY(holder_id) REFERENCES organizations(id)
);

CREATE TABLE lot_lineage(
   id SERIAL,
   quantity_contributed_kg NUMERIC(15,2) CHECK (quantity_contributed_kg >= 0) ,
   parent_lot_id INTEGER NOT NULL,
   child_lot_id INTEGER NOT NULL,
   CHECK (parent_lot_id <> child_lot_id),
   UNIQUE(parent_lot_id, child_lot_id),
   PRIMARY KEY(id),
   FOREIGN KEY(parent_lot_id) REFERENCES lots(id),
   FOREIGN KEY(child_lot_id) REFERENCES lots(id)
);

CREATE TABLE quality_checks(
   id SERIAL,
   checked_at TIMESTAMP,
   moisture_percentage NUMERIC(5,2) CHECK (moisture_percentage BETWEEN 0 AND 100) ,
   grade VARCHAR(50) ,
   result VARCHAR(50)  NOT NULL
    CHECK (result IN (
        'passed',
        'failed',
        'conditional'
    )),
   comments TEXT,
   checked_by_id INTEGER NOT NULL,
   lot_id INTEGER NOT NULL,
   PRIMARY KEY(id),
   FOREIGN KEY(checked_by_id) REFERENCES users(id),
   FOREIGN KEY(lot_id) REFERENCES lots(id)
);

CREATE TABLE shipments(
   id SERIAL,
   shipment_code VARCHAR(50) ,
   destination_country VARCHAR(50)  NOT NULL,
   planned_departure TIMESTAMP,
   actual_departure TIMESTAMP,
   status VARCHAR(50) DEFAULT 'planned' 
    CHECK (status IN (
        'planned',
        'ready',
        'in_transit',
        'delivered',
        'cancelled'
    )),
   created_at TIMESTAMP DEFAULT NOW(),
   PRIMARY KEY(id),
   UNIQUE(shipment_code)
);

CREATE TABLE shipment_lots(
   id SERIAL,
   quantity_kg NUMERIC(15,2) CHECK (quantity_kg > 0) ,
   shipment_id INTEGER NOT NULL,
   lot_id INTEGER NOT NULL,
   UNIQUE(shipment_id, lot_id),
   PRIMARY KEY(id),
   FOREIGN KEY(shipment_id) REFERENCES shipments(id),
   FOREIGN KEY(lot_id) REFERENCES lots(id)
);

CREATE TABLE qr_codes(
   id SERIAL,
   public_token VARCHAR(50) ,
   created_at TIMESTAMP DEFAULT NOW(),
   revoked_at TIMESTAMP,
   lot_id INTEGER NOT NULL,
   PRIMARY KEY(id),
   UNIQUE(public_token),
   FOREIGN KEY(lot_id) REFERENCES lots(id),
   CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE TABLE traceability_events(
   id SERIAL,
   event_code VARCHAR(50) ,
   event_type VARCHAR(50) 
    CHECK (event_type IN (
        'harvest',
        'collection',
        'transfer',
        'processing',
        'quality_check',
        'storage',
        'shipment',
        'export'
    )),
   event_date TIMESTAMP,
   recorded_at TIMESTAMP DEFAULT NOW(),
   description TEXT, 
   status VARCHAR(50) NOT NULL DEFAULT 'pending'
    CHECK (status IN (
        'pending',
        'validated',
        'rejected',
        'cancelled'
    )) ,
   validated_at TIMESTAMP,
   recorded_by_id INTEGER NOT NULL,
   location_id INTEGER NOT NULL,
   validated_by_id INTEGER,
   organization_id INTEGER,
   PRIMARY KEY(id),
   UNIQUE(event_code),
   FOREIGN KEY(recorded_by_id) REFERENCES users(id),
   FOREIGN KEY(location_id) REFERENCES locations(id),
   FOREIGN KEY(validated_by_id) REFERENCES users(id),
   FOREIGN KEY(organization_id) REFERENCES organizations(id),
   CHECK (
        (status = 'validated' AND validated_at IS NOT NULL
            AND validated_by_id IS NOT NULL)
        OR
        (status <> 'validated')
    )
);

CREATE TABLE processing_records(
   id SERIAL,
   process_type VARCHAR(50)  NOT NULL,
   start_date TIMESTAMP,
   end_date TIMESTAMP,
   input_quantity_kg NUMERIC(15,2) CHECK (input_quantity_kg >= 0)  NOT NULL,
   output_quantity_kg NUMERIC(15,2) CHECK (output_quantity_kg >= 0) ,
   loss_quantity_kg NUMERIC(15,2) CHECK (loss_quantity_kg >= 0) ,
   notes TEXT,
   event_id INTEGER NOT NULL,
   PRIMARY KEY(id),
   FOREIGN KEY(event_id) REFERENCES traceability_events(id)
);

CREATE TABLE event_lots(
   id SERIAL,
   role VARCHAR(50) 
    CHECK (role IN (
        'input',
        'output',
        'transferred'
    )),
   quantity_kg NUMERIC(15,2) CHECK (quantity_kg > 0) ,
   event_id INTEGER NOT NULL,
   lot_id INTEGER NOT NULL,
   PRIMARY KEY(id),
   FOREIGN KEY(lot_id) REFERENCES lots(id),
   FOREIGN KEY(event_id) REFERENCES traceability_events(id)
);

CREATE TABLE transfers(
   id SERIAL,
   dispatch_date TIMESTAMP,
   receipt_date TIMESTAMP,
   status VARCHAR(50) NOT NULL DEFAULT 'pending'
    CHECK (status IN (
        'pending',
        'dispatched',
        'received',
        'rejected',
        'cancelled'
    )) ,
   event_id INTEGER NOT NULL,
   from_organization_id INTEGER NOT NULL,
   to_organization_id INTEGER NOT NULL,
   origin_location_id INTEGER NOT NULL,
   destination_location_id INTEGER NOT NULL,
   PRIMARY KEY(id),
   FOREIGN KEY(event_id) REFERENCES traceability_events(id),
   FOREIGN KEY(from_organization_id) REFERENCES organizations(id),
   FOREIGN KEY(to_organization_id) REFERENCES organizations(id),
   FOREIGN KEY(origin_location_id) REFERENCES locations(id),
   FOREIGN KEY(destination_location_id) REFERENCES locations(id),
   CHECK (from_organization_id <> to_organization_id),
   CHECK (receipt_date IS NULL OR dispatch_date IS NULL
    OR receipt_date >= dispatch_date)
);